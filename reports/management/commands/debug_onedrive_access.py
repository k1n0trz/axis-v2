import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.integrations.clients import MicrosoftGraphClient


class Command(BaseCommand):
    help = "Diagnostica acceso a OneDrive con Microsoft Graph y ayuda a encontrar el archivo correcto."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", default="")
        parser.add_argument("--path", default="")
        parser.add_argument("--search", default="")

    def handle(self, *args, **options):
        tenant_id = getattr(settings, "ONEDRIVE_TENANT_ID", "")
        client_id = getattr(settings, "ONEDRIVE_CLIENT_ID", "")
        client_secret = getattr(settings, "ONEDRIVE_CLIENT_SECRET", "")
        user_id = options["user_id"] or getattr(settings, "ONEDRIVE_USER_ID", "")
        if not all([tenant_id, client_id, client_secret, user_id]):
            raise CommandError("Faltan credenciales de OneDrive o ONEDRIVE_USER_ID.")

        client = MicrosoftGraphClient(tenant_id, client_id, client_secret)
        payload = {
            "user_id": user_id,
            "drive": None,
            "children": [],
            "search_results": [],
        }

        try:
            payload["drive"] = client.get_user_drive(user_id)
        except Exception as exc:
            payload["drive_error"] = str(exc)

        if options["path"] is not None:
            try:
                payload["children"] = client.list_children(user_id, options["path"])
            except Exception as exc:
                payload["children_error"] = str(exc)

        if options["search"]:
            try:
                payload["search_results"] = client.search_drive(user_id, options["search"])
            except Exception as exc:
                payload["search_error"] = str(exc)

        self.stdout.write(json.dumps(payload, indent=2, default=str))
