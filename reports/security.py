from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.utils.cache import patch_cache_control, patch_vary_headers


PUBLIC_PATH_PREFIXES = ("/admin/", "/static/")


def robots_txt(_request):
    response = HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    return response


class AdminSessionRequiredMiddleware:
    """Keep Axis data behind an active Django admin session."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self._authorize_request(request)
        if response is None:
            response = self.get_response(request)
        return self._protect_response(request, response)

    def _authorize_request(self, request):
        path = request.path_info
        if path == "/robots.txt" or path.startswith(PUBLIC_PATH_PREFIXES):
            return None

        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.is_active and user.is_staff:
            return None

        if path.startswith("/api/"):
            return JsonResponse({"detail": "Autenticacion de administrador requerida."}, status=403)
        if user and user.is_authenticated:
            return HttpResponseForbidden("Acceso restringido al administrador de Helti.")
        return redirect_to_login(request.get_full_path(), reverse("admin:login"))

    def _protect_response(self, request, response):
        path = request.path_info
        if not path.startswith("/static/"):
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
        if not path.startswith(PUBLIC_PATH_PREFIXES) and path != "/robots.txt":
            patch_cache_control(response, private=True, no_cache=True, no_store=True, must_revalidate=True)
            patch_vary_headers(response, ("Cookie",))
        return response
