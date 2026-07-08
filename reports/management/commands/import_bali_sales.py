from django.core.management.base import BaseCommand, CommandError

from reports.services.sales_dashboard import import_bali_workbook


class Command(BaseCommand):
    help = "Importa el archivo diario de Bali con metricas web y resumen de WhatsApp."

    def add_arguments(self, parser):
        parser.add_argument("workbook_path", type=str, help="Ruta del archivo Excel de Bali")

    def handle(self, *args, **options):
        workbook_path = options["workbook_path"]
        try:
            result = import_bali_workbook(workbook_path)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Importacion Bali completada. "
                f"Metricas creadas: {result['created_metrics']}. "
                f"Metricas actualizadas: {result['updated_metrics']}. "
                f"WhatsApp creado: {result['created_whatsapp']}. "
                f"WhatsApp actualizado: {result['updated_whatsapp']}. "
                f"WhatsApp eliminado: {result['deleted_whatsapp']}. "
                f"Omitidos: {result['skipped']}."
            )
        )
