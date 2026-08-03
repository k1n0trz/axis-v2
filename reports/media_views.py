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


def stream_storage_file(path, filename=""):
    """Sirve un archivo del storage. Quien llame decide si el usuario tiene derecho.

    `protected_media` solo exige sesion de staff, asi que no sirve para archivos con
    dueño: cualquier miembro del equipo que adivinara la ruta los veria. Los adjuntos de
    la IA usan esta funcion desde una vista que primero comprueba de quien es.
    """
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
        filename=filename or posixpath.basename(normalized_path),
    )


@staff_member_required
def protected_media(request, path):
    return stream_storage_file(path)
