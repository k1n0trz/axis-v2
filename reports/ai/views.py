"""Los endpoints del chat: historial, mensaje, memorias y calificacion.

Nada de esto corre en el render de una pagina. El widget se pinta vacio y pide el
historial cuando lo abres; el mensaje va en su propio POST. Es la misma regla que nos
costo 16 s en el panel de Meta: nada bloqueante de red en el camino de la pagina.
"""
import json
import re

from django.db import transaction
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ..media_views import stream_storage_file
from ..models import AiAttachment, AiConversation, AiMemory, AiMessage
from .attachments import (
    ALLOWED_EXTENSIONS,
    AttachmentError,
    forget_attachment,
    list_attachments,
    max_size_bytes,
    save_attachment,
)
from .budget import BudgetExceeded, check_budget, cost_for, usage_today
from .context import build_system_prompt, is_ai_enabled
from .memory import forget, mark_used, memory_blocks, relevant_memories, remember
from .permissions import can_import_data, why_not_import
from .providers import AiProviderError, deepseek_client
from .spreadsheets import (
    AttachmentGone,
    ImportNotPossible,
    apply_import,
    attachment_for,
    preview_import,
)
from .tools import TOOL_SPECS, run_tool

# Cuantos turnos previos se le mandan al modelo. Los mas viejos entran comprimidos en
# `conversation.summary`, no crudos: mas historia es mas costo en cada mensaje.
HISTORY_TURNS = 12
MAX_MESSAGE_CHARS = 4000
# Vueltas de consulta por pregunta. Cada vuelta es una llamada al proveedor.
MAX_TOOL_ROUNDS = 4

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


def _answer_with_tools(client, messages, user):
    """Deja que el modelo consulte Axis antes de responder.

    Devuelve (respuesta, herramientas_usadas, tokens_entrada, tokens_salida). Los tokens
    se suman en todas las vueltas: el costo real de una respuesta con consultas es la
    suma, y cobrar solo la ultima vuelta subestimaria el gasto del dia.

    El tope de vueltas no es decorativo. Un modelo que no encuentra lo que busca
    reintenta, y sin tope una sola pregunta puede encadenar consultas hasta agotar el
    presupuesto de la persona.
    """
    conversacion = list(messages)
    herramientas = []
    entrada = 0
    salida = 0

    for _vuelta in range(MAX_TOOL_ROUNDS):
        resultado = client.chat(conversacion, tools=TOOL_SPECS)
        entrada += resultado.get("prompt_tokens") or 0
        salida += resultado.get("completion_tokens") or 0

        llamadas = resultado.get("tool_calls") or []
        if not llamadas:
            return resultado, herramientas, entrada, salida

        conversacion.append({
            "role": "assistant",
            "content": resultado.get("content") or "",
            "tool_calls": llamadas,
        })
        for llamada in llamadas:
            funcion = llamada.get("function") or {}
            nombre = funcion.get("name") or ""
            try:
                argumentos = json.loads(funcion.get("arguments") or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            datos = run_tool(user, nombre, argumentos)
            herramientas.append({"name": nombre, "arguments": argumentos})
            conversacion.append({
                "role": "tool",
                "tool_call_id": llamada.get("id") or "",
                "content": json.dumps(datos, ensure_ascii=False, default=str),
            })

    # Se acabaron las vueltas con consultas pendientes: se pide el cierre sin
    # herramientas, para que responda con lo que ya tiene en vez de dejar el hilo roto.
    conversacion.append({
        "role": "system",
        "content": "Ya no puedes hacer mas consultas. Responde con los datos que tengas "
                   "y di explicitamente que te falto verificar.",
    })
    resultado = client.chat(conversacion)
    entrada += resultado.get("prompt_tokens") or 0
    salida += resultado.get("completion_tokens") or 0
    return resultado, herramientas, entrada, salida


def _usage_payload(user):
    """El gasto del dia, en tipos que JSON entienda (cost_usd viene en Decimal)."""
    gastado = usage_today(user)
    return {"tokens": gastado["tokens"], "cost_usd": float(gastado["cost_usd"])}


def _serialize_attachment(attachment):
    return {
        "id": attachment.pk,
        "name": attachment.original_name,
        "size_kb": round(attachment.size_bytes / 1024),
        "content_type": attachment.content_type,
        "description": attachment.description,
        "uploaded_at": attachment.created_at.isoformat(),
        "url": reverse("reports:ai_attachment_download", args=[attachment.pk]),
    }


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
        result, herramientas, prompt_tokens, completion_tokens = _answer_with_tools(
            client, messages, request.user
        )
    except AiProviderError as exc:
        # El mensaje del usuario no se guarda si no hubo respuesta: al reintentar no
        # queremos que aparezca dos veces en el hilo.
        return JsonResponse({"detail": str(exc)}, status=502)

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
            tools_used=herramientas,
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


@require_POST
def ai_attachment_upload(request):
    """Recibe un archivo y lo deja disponible tambien en las proximas sesiones."""
    subido = request.FILES.get("file")
    if not subido:
        return JsonResponse({"detail": "No llego ningun archivo."}, status=400)

    try:
        attachment, era_nuevo = save_attachment(
            request.user,
            subido,
            conversation=_current_conversation(request, create=True),
            description=(request.POST.get("description") or "").strip(),
        )
    except AttachmentError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse({
        "attachment": _serialize_attachment(attachment),
        "already_had_it": not era_nuevo,
    })


@require_GET
def ai_attachments(request):
    """Los archivos que esta persona le ha pasado a la IA."""
    return JsonResponse({
        "attachments": [_serialize_attachment(a) for a in list_attachments(request.user)],
        "can_import": can_import_data(request.user),
        "why_not_import": why_not_import(request.user),
        "max_mb": max_size_bytes() // (1024 * 1024),
        "allowed": sorted(ALLOWED_EXTENSIONS),
    })


@require_http_methods(["POST", "DELETE"])
def ai_attachment_forget(request, attachment_id):
    """Lo saca de la lista. El objeto queda en el bucket por si fue un error."""
    retirados = forget_attachment(request.user, attachment_id)
    if not retirados:
        return JsonResponse({"detail": "Ese archivo no existe o ya estaba retirado."}, status=404)
    return JsonResponse({"forgotten": attachment_id})


@require_GET
def ai_attachment_download(request, attachment_id):
    """Descarga con dueño comprobado.

    No usa `protected_media` a proposito: esa vista solo exige sesion de staff, asi que
    cualquiera del equipo que adivinara la ruta veria el archivo de otra persona.
    """
    attachment = AiAttachment.objects.filter(
        pk=attachment_id, user=request.user, is_active=True
    ).first()
    if not attachment:
        raise Http404("Archivo no encontrado.")
    return stream_storage_file(attachment.file.name, filename=attachment.original_name)


@require_POST
def ai_attachment_import(request, attachment_id):
    """Carga de verdad un archivo a Axis.

    **Esto no es una herramienta del modelo.** La IA diagnostica, simula y explica; el
    boton lo aprieta una persona. Un modelo que puede escribir solo porque le dijeron
    "cargalo" no tiene ningun freno cuando entiende mal la instruccion.

    Pide `confirm=true` aparte: llegar aqui por accidente no debe escribir nada.
    """
    motivo = why_not_import(request.user)
    if motivo:
        return JsonResponse({"detail": motivo}, status=403)

    attachment = attachment_for(request.user, attachment_id)
    if not attachment:
        return JsonResponse({"detail": "Ese archivo no existe o ya lo retiraste."}, status=404)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = {}
    if payload.get("confirm") is not True:
        return JsonResponse(
            {"detail": "Falta la confirmacion explicita."}, status=400
        )

    try:
        resultado = apply_import(attachment, request.user, sheet_name=payload.get("sheet") or "")
    except (ImportNotPossible, AttachmentGone) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse({"imported": resultado})


@require_POST
def ai_attachment_preview(request, attachment_id):
    """Simula la carga desde el widget. Cualquiera la puede pedir: no escribe."""
    attachment = attachment_for(request.user, attachment_id)
    if not attachment:
        return JsonResponse({"detail": "Ese archivo no existe o ya lo retiraste."}, status=404)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = {}
    try:
        resultado = preview_import(attachment, sheet_name=payload.get("sheet") or "")
    except (ImportNotPossible, AttachmentGone) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"preview": resultado, "can_import": can_import_data(request.user)})
