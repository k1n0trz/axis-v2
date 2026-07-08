from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Carga el historico de un ano completo en Helti para luego poder filtrarlo libremente desde la UI."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=timezone.localdate().year)
        parser.add_argument("--uva-sales", action="store_true", help="Incluye WooCommerce y OneDrive de Uva.")
        parser.add_argument("--uva-ads", action="store_true", help="Incluye Meta Ads y Google Ads de Uva.")
        parser.add_argument("--bali", action="store_true", help="Incluye Shopify Bali.")
        parser.add_argument("--all", action="store_true", help="Incluye todas las fuentes configuradas.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--continue-on-error", action="store_true")
        parser.add_argument("--meta-rules", default="docs/mappings/meta-category-rules.example.json")
        parser.add_argument("--google-rules", default="docs/mappings/google-category-rules.example.json")

    def handle(self, *args, **options):
        year = int(options["year"])
        today = timezone.localdate()
        start_date = date(year, 1, 1)
        end_date = today if year == today.year else date(year, 12, 31)

        self.stdout.write(
            f"Preparando sync historico {year}: {start_date.isoformat()} a {end_date.isoformat()}",
            ending="\n",
        )

        command_args = [
            "sync_axis_history_range",
            "--date-from",
            start_date.isoformat(),
            "--date-to",
            end_date.isoformat(),
            "--meta-rules",
            options["meta_rules"],
            "--google-rules",
            options["google_rules"],
        ]

        if options["all"] or not any([options["uva_sales"], options["uva_ads"], options["bali"]]):
            command_args.append("--all")
        else:
            if options["uva_sales"]:
                command_args.append("--uva-sales")
            if options["uva_ads"]:
                command_args.append("--uva-ads")
            if options["bali"]:
                command_args.append("--bali")

        if options["dry_run"]:
            command_args.append("--dry-run")
        if options["continue_on_error"]:
            command_args.append("--continue-on-error")

        call_command(*command_args)
