import mimetypes
import posixpath

from django.contrib.admin.views.decorators import staff_member_required
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
    if not default_storage.exists(normalized_path):
        raise Http404("Archivo no encontrado.")

    content_type, _ = mimetypes.guess_type(normalized_path)
    content_type = content_type or "application/octet-stream"
    inline = content_type in INLINE_CONTENT_TYPES
    return FileResponse(
        default_storage.open(normalized_path, "rb"),
        content_type=content_type,
        as_attachment=not inline,
        filename=posixpath.basename(normalized_path),
    )
