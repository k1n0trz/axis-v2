"""Los dos endpoints del chat: leer el historial y mandar un mensaje.

Nada de esto corre en el render de una pagina. El widget se pinta vacio y pide el
historial cuando lo abres; el mensaje va en su propio POST. Es la misma regla que nos
costo 16 s en el panel de Meta: nada bloqueante de red en el camino de la pagina.
"""
import json

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from ..models import AiConversation, AiMessage
from .budget import BudgetExceeded, check_budget, cost_for, usage_today
from .context import build_system_prompt, is_ai_enabled
from .providers import AiProviderError, deepseek_client

# Cuantos turnos previos se le mandan al modelo. Mas historia es mas costo por mensaje
# y el modelo tampoco la aprovecha: la memoria de verdad llega en la Etapa D.
HISTORY_TURNS = 12
MAX_MESSAGE_CHARS = 4000


def _usage_payload(user):
    """El gasto del dia, en tipos que JSON entienda (cost_usd viene en Decimal)."""
    gastado = usage_today(user)
    return {"tokens": gastado["tokens"], "cost_usd": float(gastado["cost_usd"])}


def _serialize(message):
    return {
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
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
        .order_by("-created_at")[:HISTORY_TURNS]
    )
    history.reverse()

    messages = [{"role": "system", "content": build_system_prompt(request.user)}]
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

    return JsonResponse({
        "conversation_id": conversation.id,
        "reply": _serialize(reply),
        "usage": _usage_payload(request.user),
    })
