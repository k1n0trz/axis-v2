import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from reports.services.google_ads_import import import_google_ads_workbook


class Command(BaseCommand):
    help = "Importa un workbook de Google Ads en el formato actual de Uva y Bali."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--uva-sheet", default="uva")
        parser.add_argument("--bali-sheet", default="bali")

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])
        if not file_path.exists():
            raise CommandError(f"No existe el archivo: {file_path}")

        with file_path.open("rb") as workbook_file:
            result = import_google_ads_workbook(
                workbook_file,
                file_path.name,
                uva_sheet=options["uva_sheet"],
                bali_sheet=options["bali_sheet"],
            )

        self.stdout.write(json.dumps(result, indent=2, default=str))
