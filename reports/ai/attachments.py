"""Archivos que el usuario le pasa a la IA y siguen ahi la semana siguiente.

Lo que se valida y por que:

**La extension, no el `Content-Type` que manda el navegador.** Ese encabezado lo pone el
cliente y se puede escribir a mano. Si dejaramos entrar lo que diga, un `.html` subido
como `text/csv` quedaria servido desde el origen de Axis.

**El tamaño, antes de leer el archivo completo.** `UploadedFile.size` viene del
encabezado, pero Django ya escribio el temporal, asi que se compara contra el tope antes
de calcular el hash y no despues.

**El hash, para no duplicar.** Volver a subir el mismo archivo devuelve el que ya estaba.
Un Excel que alguien reenvia cada dia no debe dejar treinta objetos en el bucket.
"""
import hashlib

from django.conf import settings
from django.utils.text import get_valid_filename

from ..models import AiAttachment

# Lo que la IA va a poder leer en la Etapa G, mas lo que sirve de adjunto. Nada
# ejecutable ni interpretable por el navegador: sin .html, .svg ni .js.
ALLOWED_EXTENSIONS = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".json": "application/json",
}
MAX_SIZE_BYTES = 15 * 1024 * 1024
MAX_ACTIVE_PER_USER = 60
HASH_CHUNK = 1024 * 1024


class AttachmentError(ValueError):
    """Archivo rechazado. El mensaje se le muestra al usuario tal cual."""


def _extension(nombre):
    resto = (nombre or "").lower()
    punto = resto.rfind(".")
    return resto[punto:] if punto != -1 else ""


def _hash_and_size(archivo):
    """sha256 y tamaño real, leyendo por trozos para no cargar 15 MB en memoria."""
    digest = hashlib.sha256()
    total = 0
    archivo.seek(0)
    for trozo in iter(lambda: archivo.read(HASH_CHUNK), b""):
        digest.update(trozo)
        total += len(trozo)
    archivo.seek(0)
    return digest.hexdigest(), total


def _stored(attachment):
    """Si el contenido sigue en el storage. La fila y el objeto pueden divergir."""
    if not attachment.file:
        return False
    try:
        return attachment.file.storage.exists(attachment.file.name)
    except (OSError, ValueError):
        return False


def max_size_bytes():
    return int(getattr(settings, "AI_ATTACHMENT_MAX_BYTES", MAX_SIZE_BYTES) or MAX_SIZE_BYTES)


def save_attachment(user, uploaded, conversation=None, description=""):
    """Guarda el archivo o devuelve el que ya estaba con el mismo contenido.

    Devuelve (attachment, era_nuevo).
    """
    nombre = get_valid_filename(uploaded.name or "archivo")
    extension = _extension(nombre)
    if extension not in ALLOWED_EXTENSIONS:
        permitidas = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise AttachmentError(f"No acepto archivos '{extension or 'sin extension'}'. Permitidos: {permitidas}.")

    tope = max_size_bytes()
    if (uploaded.size or 0) > tope:
        raise AttachmentError(f"El archivo pesa mas de {tope // (1024 * 1024)} MB.")

    firma, tamano = _hash_and_size(uploaded)
    if tamano == 0:
        raise AttachmentError("El archivo llego vacio.")
    if tamano > tope:
        # El encabezado decia otra cosa: el tamaño de verdad es el que se leyo.
        raise AttachmentError(f"El archivo pesa mas de {tope // (1024 * 1024)} MB.")

    existente = AiAttachment.objects.filter(user=user, sha256=firma).first()
    if existente and not _stored(existente):
        # La fila esta pero el contenido no. Devolverla daria un archivo que no se puede
        # abrir, y el error saldria mucho despues, al intentar leerlo. Se vuelve a
        # guardar el contenido sobre la misma fila.
        existente.file.save(f"{user.pk}/{firma[:16]}{extension}", uploaded, save=False)
        existente.is_active = True
        existente.size_bytes = tamano
        existente.save()
        return existente, False
    if existente:
        campos = []
        if not existente.is_active:
            existente.is_active = True
            campos.append("is_active")
        if description and description != existente.description:
            existente.description = description[:300]
            campos.append("description")
        if campos:
            existente.save(update_fields=[*campos, "updated_at"])
        return existente, False

    attachment = AiAttachment(
        user=user,
        conversation=conversation,
        original_name=nombre[:255],
        # El tipo lo decidimos por la extension que ya validamos, no por el encabezado.
        content_type=ALLOWED_EXTENSIONS[extension],
        size_bytes=tamano,
        sha256=firma,
        description=description[:300],
    )
    # El nombre en el bucket lleva el hash: dos personas pueden subir "ventas.xlsx" y no
    # se pisan, y el nombre no delata nada de otro usuario.
    attachment.file.save(f"{user.pk}/{firma[:16]}{extension}", uploaded, save=False)
    attachment.save()
    _trim_to_limit(user)
    return attachment, True


def _trim_to_limit(user):
    activos = AiAttachment.objects.filter(user=user, is_active=True)
    sobrantes = activos.count() - MAX_ACTIVE_PER_USER
    if sobrantes <= 0:
        return
    # Se retiran los mas viejos, pero el objeto en el bucket no se borra: si alguien
    # retiro por error, el archivo sigue ahi.
    viejos = list(activos.order_by("created_at").values_list("pk", flat=True)[:sobrantes])
    AiAttachment.objects.filter(pk__in=viejos).update(is_active=False)


def list_attachments(user):
    return AiAttachment.objects.filter(user=user, is_active=True)


def forget_attachment(user, attachment_id):
    """Lo retira de la lista. No borra el objeto del bucket."""
    return AiAttachment.objects.filter(user=user, pk=attachment_id, is_active=True).update(
        is_active=False
    )
