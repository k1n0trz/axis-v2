import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.services.google_ads_import import import_google_ads_workbook, source_name_from_drive_path
from reports.utils import onedrive


class Command(BaseCommand):
    help = "Descarga el workbook de Google Ads desde OneDrive e importa sus hojas de Uva y Bali."

    def add_arguments(self, parser):
        parser.add_argument("--drive-path", default="")
        parser.add_argument("--uva-sheet", default="uva")
        parser.add_argument("--bali-sheet", default="bali")
        parser.add_argument("--drive-user-id", default="")

    def handle(self, *args, **options):
        drive_path = options["drive_path"] or getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", "")
        if not drive_path:
            raise CommandError("Falta ONEDRIVE_GOOGLE_ADS_FILE_PATH o --drive-path.")

        if not all(
            [
                getattr(settings, "ONEDRIVE_CLIENT_ID", ""),
                getattr(settings, "ONEDRIVE_CLIENT_SECRET", ""),
                getattr(settings, "ONEDRIVE_TENANT_ID", ""),
                getattr(settings, "ONEDRIVE_REFRESH_TOKEN", ""),
            ]
        ):
            raise CommandError("Faltan credenciales delegadas de OneDrive para descargar Google Ads.")

        token_payload = onedrive.refresh_access_token()
        drive_user_id = options["drive_user_id"] or getattr(settings, "ONEDRIVE_USER_ID", "")
        buffer = onedrive.download_file_content_by_path(
            token_payload["access_token"],
            drive_path,
            user_id=drive_user_id or None,
        )
        source_name = source_name_from_drive_path(drive_path)
        result = import_google_ads_workbook(
            buffer,
            source_name,
            uva_sheet=options["uva_sheet"],
            bali_sheet=options["bali_sheet"],
        )

        self.stdout.write(
            json.dumps(
                {
                    "source_file": source_name,
                    "drive_path": drive_path,
                    "result": result,
                },
                indent=2,
                default=str,
            )
        )
