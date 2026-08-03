"""Los endpoints del chat: historial, mensaje, memorias y calificacion.

Nada de esto corre en el render de una pagina. El widget se pinta vacio y pide el
historial cuando lo abres; el mensaje va en su propio POST. Es la misma regla que nos
costo 16 s en el panel de Meta: nada bloqueante de red en el camino de la pagina.
"""
import json
import re

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ..models import AiConversation, AiMemory, AiMessage
from .budget import BudgetExceeded, check_budget, cost_for, usage_today
from .context import build_system_prompt, is_ai_enabled
from .memory import forget, mark_used, memory_blocks, relevant_memories, remember
from .providers import AiProviderError, deepseek_client

# Cuantos turnos previos se le mandan al modelo. Los mas viejos entran comprimidos en
# `conversation.summary`, no crudos: mas historia es mas costo en cada mensaje.
HISTORY_TURNS = 12
MAX_MESSAGE_CHARS = 4000

# "Recuerda que trabajamos con Uva" -> se guarda tal cual, sin llamar al modelo.
PEDIDO_DE_MEMORIA = re.compile(
    r"^\s*(?:recuerda|recorda|acuerdate|acu[eé]rdate|ten en cuenta|tene en cuenta|"
    r"no olvides|anota)\s+(?:que\s+)?(.{12,400})$",
    re.IGNORECASE | re.DOTALL,
)


def remember_explicit_request(user, text, conversation=None):
    """Si el mensaje empieza con 'recuerda que...', guarda el resto como nota."""
    coincidencia = PEDIDO_DE_MEMORIA.match(text or "")
    if not coincidencia:
        return None
    return remember(
        user,
        coincidencia.group(1).strip().rstrip(".").strip(),
        kind=AiMemory.Kind.PREFERENCE,
        origin=AiMemory.Origin.EXPLICIT,
        conversation=conversation,
    )


def _usage_payload(user):
    """El gasto del dia, en tipos que JSON entienda (cost_usd viene en Decimal)."""
    gastado = usage_today(user)
    return {"tokens": gastado["tokens"], "cost_usd": float(gastado["cost_usd"])}


def _serialize(message):
    return {
        "id": message.pk,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "feedback": message.feedback,
    }


def _current_conversation(request, create=False):
    """La conversacion abierta de este usuario en esta sesion."""
    if not request.session.session_key:
        if not create:
            return None
        request.session.save()
    session_key = request.session.session_key or ""
    existing = (
        AiConversation.objects.filter(user=request.user, session_key=session_key)
        .order_by("-updated_at")
        .first()
    )
    if existing or not create:
        return existing
    return AiConversation.objects.create(user=request.user, session_key=session_key)


@require_GET
def ai_history(request):
    """Historial de la conversacion en curso. Sin llamadas al proveedor."""
    conversation = _current_conversation(request)
    messages = []
    if conversation:
        messages = [
            _serialize(m)
            for m in conversation.messages.filter(role__in=("user", "assistant")).order_by("created_at")
        ]
    return JsonResponse({
        "enabled": is_ai_enabled(),
        "conversation_id": conversation.id if conversation else None,
        "messages": messages,
        "usage": _usage_payload(request.user),
    })


@require_POST
def ai_chat(request):
    """Recibe un mensaje, responde y deja los dos turnos guardados."""
    if not is_ai_enabled():
        return JsonResponse(
            {"detail": "El asistente no esta configurado en este entorno."}, status=503
        )

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Cuerpo invalido."}, status=400)

    text = (payload.get("message") or "").strip()
    if not text:
        return JsonResponse({"detail": "Escribe algo primero."}, status=400)
    if len(text) > MAX_MESSAGE_CHARS:
        return JsonResponse(
            {"detail": f"El mensaje no puede pasar de {MAX_MESSAGE_CHARS} caracteres."},
            status=400,
        )

    try:
        check_budget(request.user)
    except BudgetExceeded as exc:
        return JsonResponse({"detail": str(exc), "budget_exceeded": True}, status=429)

    conversation = _current_conversation(request, create=True)
    history = list(
        conversation.messages.filter(role__in=("user", "assistant"))
        .exclude(pk__lte=conversation.summarized_until)
        .order_by("-created_at")[:HISTORY_TURNS]
    )
    history.reverse()

    # Lo que el usuario pide recordar se guarda ya, sin gastar otra llamada: viene dicho.
    explicit = remember_explicit_request(request.user, text, conversation)

    recalled = relevant_memories(request.user, text)
    contexto, reglas = memory_blocks(recalled)

    messages = [{"role": "system", "content": build_system_prompt(request.user, rules=reglas)}]
    if conversation.summary:
        messages.append({
            "role": "system",
            "content": f"Resumen de lo hablado antes en esta conversacion:\n{conversation.summary}",
        })
    if contexto:
        messages.append({"role": "system", "content": contexto})
    messages += [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": text})

    client = deepseek_client()
    try:
        result = client.chat(messages)
    except AiProviderError as exc:
        # El mensaje del usuario no se guarda si no hubo respuesta: al reintentar no
        # queremos que aparezca dos veces en el hilo.
        return JsonResponse({"detail": str(exc)}, status=502)

    prompt_tokens = result.get("prompt_tokens") or 0
    completion_tokens = result.get("completion_tokens") or 0
    cost = cost_for(prompt_tokens, completion_tokens)

    with transaction.atomic():
        AiMessage.objects.create(conversation=conversation, role="user", content=text)
        reply = AiMessage.objects.create(
            conversation=conversation,
            role="assistant",
            content=result.get("content") or "",
            model=result.get("model") or "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
        )
        if not conversation.title:
            conversation.title = text[:80]
        conversation.save(update_fields=["title", "updated_at"])

    mark_used(recalled)

    return JsonResponse({
        "conversation_id": conversation.id,
        "reply": _serialize(reply),
        "usage": _usage_payload(request.user),
        "recalled": len(recalled),
        "remembered": explicit.content if explicit else "",
    })


@require_GET
def ai_memories(request):
    """Lo que la IA cree saber de esta persona. Tiene que poder leerlo."""
    memorias = AiMemory.objects.filter(user=request.user, is_active=True)
    return JsonResponse({
        "memories": [
            {
                "id": m.pk,
                "kind": m.get_kind_display(),
                "origin": m.get_origin_display(),
                "content": m.content,
                "times_used": m.times_used,
            }
            for m in memorias
        ]
    })


@require_http_methods(["POST", "DELETE"])
def ai_memory_forget(request, memory_id):
    """Retira una nota. Soft-delete: nadie tiene que adivinar que existio."""
    retiradas = forget(request.user, memory_id)
    if not retiradas:
        return JsonResponse({"detail": "Esa nota no existe o ya estaba retirada."}, status=404)
    return JsonResponse({"forgotten": memory_id})


@require_POST
def ai_feedback(request):
    """Pulgar arriba o abajo. Un pulgar abajo excluye la respuesta de la distilacion."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Cuerpo invalido."}, status=400)

    valor = (payload.get("feedback") or "").strip()
    if valor not in {AiMessage.Feedback.UP, AiMessage.Feedback.DOWN, ""}:
        return JsonResponse({"detail": "Calificacion invalida."}, status=400)

    actualizados = AiMessage.objects.filter(
        pk=payload.get("message_id"), conversation__user=request.user, role="assistant"
    ).update(feedback=valor)
    if not actualizados:
        return JsonResponse({"detail": "Ese mensaje no existe."}, status=404)
    return JsonResponse({"feedback": valor})
