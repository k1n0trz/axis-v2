from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from reports.services.comfama_import import import_comfama_ad_spend_workbook, import_comfama_sales_workbook
from reports.services.sales_dashboard import parse_excel_date


class Command(BaseCommand):
    help = "Importa ventas/precios y, opcionalmente, pauta diaria de Uva Comfama desde Excel."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--end-date", default="")
        parser.add_argument("--sales-sheet", default="Hoja1")
        parser.add_argument("--ad-sheet", default="Hoja2")
        parser.add_argument("--skip-sales", action="store_true")
        parser.add_argument("--skip-ad-spend", action="store_true")
        parser.add_argument("--keep-existing-source", action="store_true")
        parser.add_argument("--replace-all-sales", action="store_true")

    def handle(self, *args, **options):
        file_path = Path(options["file_path"])
        if not file_path.exists():
            raise CommandError(f"No existe el archivo: {file_path}")

        end_date = parse_excel_date(options["end_date"]) if options["end_date"] else date.max
        messages = []

        if not options["skip_sales"]:
            if options["replace_all_sales"]:
                from reports.models import ComfamaSale

                deleted_sales, _ = ComfamaSale.objects.all().delete()
                messages.append(f"Ventas existentes eliminadas {deleted_sales}.")
            with file_path.open("rb") as workbook_file:
                result = import_comfama_sales_workbook(
                    workbook_file,
                    file_path.name,
                    sheet_name=options["sales_sheet"],
                    end_date=end_date,
                    replace_source=not options["keep_existing_source"],
                )
            messages.append(
                "Ventas: "
                f"referencias creadas {result['created_refs']}, actualizadas {result['updated_refs']}, inferidas {result['inferred_refs']}; "
                f"ventas creadas {result['created_sales']}, actualizadas {result['updated_sales']}, eliminadas {result['deleted_sales']}, omitidas {result['skipped_sales']}."
            )

        if not options["skip_ad_spend"]:
            with file_path.open("rb") as workbook_file:
                result = import_comfama_ad_spend_workbook(workbook_file, file_path.name, sheet_name=options["ad_sheet"], end_date=end_date)
            messages.append(
                f"Pauta diaria: gastos creados {result['created']}, actualizados {result['updated']}; "
                f"metricas por categoria creadas {result['metric_created']}, actualizadas {result['metric_updated']} para {result['business_unit']}."
            )

        self.stdout.write(self.style.SUCCESS("Importacion Comfama completada. " + " ".join(messages)))
