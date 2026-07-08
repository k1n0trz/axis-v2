from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.test import Client


class Command(BaseCommand):
    help = "Render a page as a specific user using Django's test client."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("path")

    def handle(self, *args, **options):
        user = User.objects.get(username=options["username"])
        client = Client(HTTP_HOST="axis-temp-176676286159.us-central1.run.app")
        client.force_login(user)
        path = options["path"].replace("__AMP__", "&")
        response = client.get(path, secure=True, follow=True)
        self.stdout.write(f"STATUS={response.status_code}")
        self.stdout.write(f"LENGTH={len(response.content)}")
        content = response.content.decode("utf-8", errors="ignore")
        self.stdout.write(f"HAS_METAS={ 'Metas' in content }")
        self.stdout.write(f"HAS_IMPORT={ 'Importar Excel' in content }")
