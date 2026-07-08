import json
from datetime import date
from pathlib import PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.services.comfama_import import import_comfama_sales_workbook
from reports.utils import onedrive


class Command(BaseCommand):
    help = "Descarga el archivo de ventas Comfama desde OneDrive e importa sus ventas a Helti."

    def add_arguments(self, parser):
        parser.add_argument("--drive-path", default="")
        parser.add_argument("--sheet", default="Hoja1")
        parser.add_argument("--end-date", default="")
        parser.add_argument("--drive-user-id", default="")
        parser.add_argument("--keep-existing-source", action="store_true")

    def handle(self, *args, **options):
        drive_path = options["drive_path"] or getattr(settings, "ONEDRIVE_SHARED_COMFAMA_FILE_PATH", "")
        if not drive_path:
            raise CommandError("Falta ONEDRIVE_SHARED_COMFAMA_FILE_PATH o --drive-path.")

        if not all(
            [
                getattr(settings, "ONEDRIVE_CLIENT_ID", ""),
                getattr(settings, "ONEDRIVE_CLIENT_SECRET", ""),
                getattr(settings, "ONEDRIVE_TENANT_ID", ""),
                getattr(settings, "ONEDRIVE_REFRESH_TOKEN", ""),
            ]
        ):
            raise CommandError("Faltan credenciales delegadas de OneDrive para descargar ventas Comfama.")

        end_date = date.fromisoformat(options["end_date"]) if options["end_date"] else date.max
        token_payload = onedrive.refresh_access_token()
        drive_user_id = options["drive_user_id"] or getattr(settings, "ONEDRIVE_USER_ID", "")
        buffer = onedrive.download_file_content_by_path(
            token_payload["access_token"],
            drive_path,
            user_id=drive_user_id or None,
        )
        source_name = PurePosixPath(drive_path).name

        result = import_comfama_sales_workbook(
            buffer,
            source_name,
            sheet_name=options["sheet"],
            end_date=end_date,
            replace_source=not options["keep_existing_source"],
        )

        self.stdout.write(
            json.dumps(
                {
                    "source_file": source_name,
                    "drive_path": drive_path,
                    "sheet": options["sheet"],
                    "end_date": end_date.isoformat() if end_date != date.max else "",
                    "result": result,
                },
                indent=2,
                default=str,
            )
        )
