from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from reports.services.sales_dashboard import import_uva_sales_workbook


class Command(BaseCommand):
    help = "Importa ventas detalladas de Uva desde el Excel de despachos de Colombia y Ecuador."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", help="Ruta al archivo Excel de despachos.")

    def handle(self, *args, **options):
        workbook_path = Path(options["xlsx_path"]).expanduser()
        if not workbook_path.exists():
            raise CommandError(f"No existe el archivo: {workbook_path}")

        stats = import_uva_sales_workbook(workbook_path)
        self.stdout.write(
            self.style.SUCCESS(
                f"Importacion completada. Creadas: {stats['created']}, actualizadas: {stats['updated']}, omitidas: {stats['skipped']}."
            )
        )
        for item in stats["sheets"]:
            self.stdout.write(f"- {item['sheet']}: {item['rows']} filas procesadas")
