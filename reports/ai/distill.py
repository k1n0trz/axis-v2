"""Sacar de una conversacion lo que vale la pena recordar.

Esto **no** corre dentro del chat. Destilar cuesta una llamada extra, y cobrarsela al
usuario en cada mensaje para adivinar si dijo algo memorable es caro y lento. Corre
despues, por lotes, en `distill_ai_memories` (lo lanza el job diario).

Lo que el usuario pide recordar explicitamente ("recuerda que...") no pasa por aqui:
eso se guarda en el momento, sin llamar al modelo, porque ya viene dicho.
"""
import json

from django.utils import timezone

from ..models import AiMemory, AiMessage
from .memory import remember
from .providers import AiProviderError, deepseek_client

# Turnos que quedan fuera del resumen: los recientes se mandan completos.
KEEP_RECENT = 6
SUMMARY_TRIGGER = 14

INSTRUCCION_MEMORIAS = """Lee esta conversacion entre una persona y el asistente de un tablero de datos.

Extrae SOLO lo que sirva en conversaciones futuras con esa persona:
- preference: como quiere que se le trabaje o se le responda
- style: como se comunica (largo/corto, tecnico/llano)
- context: hechos estables de su operacion que dijo el usuario
- decision: decisiones que tomo y hay que respetar

Reglas:
- No extraigas cifras, fechas ni resultados puntuales: eso cambia y envejece mal.
- No extraigas nada que ya sea obvio del cargo o del tablero.
- Si la conversacion no tiene nada memorable, devuelve una lista vacia.
- Las notas preference y style, en imperativo ("Responde en dos frases"): son reglas
  que el asistente va a cumplir, no descripciones de la persona.
- Las notas context y decision, en tercera persona ("Factura en COP aunque...").
- Cada nota en una frase, en español. Maximo 4 notas.

Responde SOLO con JSON: {"memories": [{"kind": "...", "content": "..."}]}"""

INSTRUCCION_RESUMEN = """Resume esta parte de una conversacion en maximo 6 lineas, en español.
Conserva lo que se decidio y lo que quedo pendiente. Omite los saludos.
Responde solo con el resumen, sin encabezados."""


def _conversation_text(messages):
    etiquetas = {"user": "Persona", "assistant": "Asistente"}
    return "\n\n".join(
        f"{etiquetas.get(m.role, m.role)}: {m.content}" for m in messages if m.content
    )


def distill_conversation(conversation, client=None):
    """Guarda las notas que salgan de la conversacion. Devuelve las creadas."""
    mensajes = list(
        conversation.messages.filter(role__in=("user", "assistant")).order_by("created_at")
    )
    if not any(m.role == "user" for m in mensajes):
        return []

    # Un pulgar abajo dice que esa respuesta no sirvio: no queremos aprender de ella.
    rechazados = {m.pk for m in mensajes if m.feedback == AiMessage.Feedback.DOWN}
    utiles = [m for m in mensajes if m.pk not in rechazados]

    cliente = client or deepseek_client()
    try:
        respuesta = cliente.chat(
            [
                {"role": "system", "content": INSTRUCCION_MEMORIAS},
                {"role": "user", "content": _conversation_text(utiles)},
            ],
            max_tokens=600,
        )
    except AiProviderError:
        # Un fallo del proveedor no debe marcar la conversacion como destilada: se
        # vuelve a intentar mañana.
        return []

    candidatas = _parse_memories(respuesta.get("content") or "")
    validas = {k for k, _ in AiMemory.Kind.choices}
    creadas = []
    for item in candidatas:
        kind = item.get("kind") if item.get("kind") in validas else AiMemory.Kind.CONTEXT
        memoria = remember(
            conversation.user,
            item.get("content") or "",
            kind=kind,
            origin=AiMemory.Origin.DISTILLED,
            conversation=conversation,
        )
        if memoria:
            creadas.append(memoria)

    conversation.distilled_at = timezone.now()
    conversation.save(update_fields=["distilled_at", "updated_at"])
    return creadas


def _parse_memories(raw):
    """El modelo a veces envuelve el JSON en ```json: no vale tumbar el lote por eso."""
    texto = raw.strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1] if "```" in texto[3:] else texto[3:]
        texto = texto.removeprefix("json").strip()
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return []
    items = datos.get("memories") if isinstance(datos, dict) else datos
    return [i for i in (items or []) if isinstance(i, dict)][:4]


def summarize_conversation(conversation, client=None):
    """Comprime los turnos viejos para no mandar la historia completa cada vez."""
    mensajes = list(
        conversation.messages.filter(role__in=("user", "assistant")).order_by("created_at")
    )
    if len(mensajes) < SUMMARY_TRIGGER:
        return False

    a_resumir = [m for m in mensajes[:-KEEP_RECENT] if m.pk > conversation.summarized_until]
    if not a_resumir:
        return False

    previo = f"Resumen previo:\n{conversation.summary}\n\n" if conversation.summary else ""
    cliente = client or deepseek_client()
    try:
        respuesta = cliente.chat(
            [
                {"role": "system", "content": INSTRUCCION_RESUMEN},
                {"role": "user", "content": previo + _conversation_text(a_resumir)},
            ],
            max_tokens=400,
        )
    except AiProviderError:
        return False

    resumen = (respuesta.get("content") or "").strip()
    if not resumen:
        return False

    conversation.summary = resumen
    conversation.summarized_until = a_resumir[-1].pk
    conversation.save(update_fields=["summary", "summarized_until", "updated_at"])
    return True
