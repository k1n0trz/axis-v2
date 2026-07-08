from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from reports.media_views import protected_media
from reports.security import robots_txt

urlpatterns = [
    path("admin/", admin.site.urls),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("", include("reports.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", protected_media),
    ]
