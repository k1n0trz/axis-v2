import mimetypes
import posixpath

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404


# Solo estos tipos se muestran en linea. Todo lo demas se descarga, para que un
# archivo subido no se pueda ejecutar como documento en el origen de Axis.
INLINE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}


@staff_member_required
def protected_media(request, path):
    normalized_path = posixpath.normpath(path).lstrip("/")
    if not normalized_path or normalized_path == "." or normalized_path.startswith("../"):
        raise Http404("Archivo no encontrado.")
    try:
        if not default_storage.exists(normalized_path):
            raise Http404("Archivo no encontrado.")
        archivo = default_storage.open(normalized_path, "rb")
    except (SuspiciousFileOperation, OSError, ValueError) as exc:
        # Una ruta absoluta ("C:/Windows/win.ini") sobrevive a normpath y el storage la
        # rechaza con SuspiciousFileOperation, que salia como HTTP 500. Pedir un archivo
        # que no se puede servir es un 404, no un error del servidor: un 500 ademas
        # delata que la ruta llego mas lejos de lo que deberia.
        raise Http404("Archivo no encontrado.") from exc

    content_type, _ = mimetypes.guess_type(normalized_path)
    content_type = content_type or "application/octet-stream"
    inline = content_type in INLINE_CONTENT_TYPES
    return FileResponse(
        archivo,
        content_type=content_type,
        as_attachment=not inline,
        filename=posixpath.basename(normalized_path),
    )
