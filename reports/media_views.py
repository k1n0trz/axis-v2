import mimetypes
import posixpath

from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404


@staff_member_required
def protected_media(request, path):
    normalized_path = posixpath.normpath(path).lstrip("/")
    if not normalized_path or normalized_path == "." or normalized_path.startswith("../"):
        raise Http404("Archivo no encontrado.")
    if not default_storage.exists(normalized_path):
        raise Http404("Archivo no encontrado.")

    content_type, _ = mimetypes.guess_type(normalized_path)
    return FileResponse(default_storage.open(normalized_path, "rb"), content_type=content_type or "application/octet-stream")
