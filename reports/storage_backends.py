from urllib.parse import urljoin

from django.conf import settings
from django.utils.encoding import filepath_to_uri
from storages.backends.gcloud import GoogleCloudStorage


class AxisGoogleCloudMediaStorage(GoogleCloudStorage):
    bucket_name = settings.GS_BUCKET_NAME
    location = settings.GS_MEDIA_LOCATION
    file_overwrite = False

    def url(self, name, parameters=None, expire=None):
        return urljoin(settings.MEDIA_URL, filepath_to_uri(name))
