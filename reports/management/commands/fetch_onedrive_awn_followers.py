import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.management.commands.import_awn_followers import import_awn_followers_workbook
from reports.services.google_ads_import import source_name_from_drive_path
from reports.services.sales_dashboard import parse_excel_date
from reports.utils import onedrive


class Command(BaseCommand):
    help = "Descarga el Excel de seguidores Awn Internacional desde OneDrive y completa visitas/seguidores preservando inversion de Meta."

    def add_arguments(self, parser):
        parser.add_argument("--drive-path", default="")
        parser.add_argument("--sheet", default="Seguidores Awn Internacional")
        parser.add_argument("--end-date", default="")
        parser.add_argument("--drive-user-id", default="")

    def handle(self, *args, **options):
        drive_path = options["drive_path"] or getattr(settings, "ONEDRIVE_AWARENESS_FILE_PATH", "")
        if not drive_path:
            raise CommandError("Falta ONEDRIVE_AWARENESS_FILE_PATH o --drive-path.")
        if not all(
            [
                getattr(settings, "ONEDRIVE_CLIENT_ID", ""),
                getattr(settings, "ONEDRIVE_CLIENT_SECRET", ""),
                getattr(settings, "ONEDRIVE_TENANT_ID", ""),
                getattr(settings, "ONEDRIVE_REFRESH_TOKEN", ""),
            ]
        ):
            raise CommandError("Faltan credenciales delegadas de OneDrive para descargar Awareness.")

        token_payload = onedrive.refresh_access_token()
        drive_user_id = options["drive_user_id"] or getattr(settings, "ONEDRIVE_USER_ID", "")
        buffer = onedrive.download_file_content_by_path(token_payload["access_token"], drive_path, user_id=drive_user_id or None)
        source_name = source_name_from_drive_path(drive_path)
        end_date = parse_excel_date(options["end_date"]) if options["end_date"] else None
        result = import_awn_followers_workbook(
            buffer,
            source_name,
            sheet_name=options["sheet"],
            end_date=end_date,
            preserve_spend=True,
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
