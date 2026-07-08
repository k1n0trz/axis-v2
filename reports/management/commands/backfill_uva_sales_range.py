import json
from datetime import date, timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


def iter_dates(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


class Command(BaseCommand):
    help = "Carga ventas Uva por rango de fechas para WooCommerce y OneDrive sin ir dia por dia manualmente."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", required=True)
        parser.add_argument("--date-to", required=True)
        parser.add_argument("--include-woocommerce-co", action="store_true")
        parser.add_argument("--include-woocommerce-mx", action="store_true")
        parser.add_argument("--include-onedrive-co", action="store_true")
        parser.add_argument("--include-onedrive-ec", action="store_true")
        parser.add_argument("--all-sales", action="store_true", help="Incluye WooCommerce CO/MX y OneDrive CO/EC si estan configurados.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--continue-on-error", action="store_true")

    def handle(self, *args, **options):
        start_date = date.fromisoformat(options["date_from"])
        end_date = date.fromisoformat(options["date_to"])
        if start_date > end_date:
            raise ValueError("--date-from no puede ser mayor que --date-to.")

        include_woocommerce_co = options["include_woocommerce_co"]
        include_woocommerce_mx = options["include_woocommerce_mx"]
        include_onedrive_co = options["include_onedrive_co"]
        include_onedrive_ec = options["include_onedrive_ec"]

        if options["all_sales"] or not any([include_woocommerce_co, include_woocommerce_mx, include_onedrive_co, include_onedrive_ec]):
            include_woocommerce_co = bool(getattr(settings, "WOOCOMMERCE_CO_BASE_URL", ""))
            include_woocommerce_mx = bool(getattr(settings, "WOOCOMMERCE_MX_BASE_URL", ""))
            include_onedrive_co = bool(getattr(settings, "ONEDRIVE_WHATSAPP_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""))
            include_onedrive_ec = bool(getattr(settings, "ONEDRIVE_ECUADOR_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""))

        plan = []
        for target_date in iter_dates(start_date, end_date):
            day = target_date.isoformat()
            if include_woocommerce_co:
                plan.append(
                    {
                        "source": "woocommerce-co",
                        "date": day,
                        "command": [
                            "fetch_woocommerce_sales",
                            "--date",
                            day,
                            "--country",
                            "CO",
                            "--sync-axis",
                        ],
                    }
                )
            if include_woocommerce_mx:
                plan.append(
                    {
                        "source": "woocommerce-mx",
                        "date": day,
                        "command": [
                            "fetch_woocommerce_sales",
                            "--date",
                            day,
                            "--country",
                            "MX",
                            "--currency",
                            "MXN",
                            "--sync-axis",
                        ],
                    }
                )
            if include_onedrive_co:
                drive_path = getattr(settings, "ONEDRIVE_WHATSAPP_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", "")
                plan.append(
                    {
                        "source": "onedrive-co",
                        "date": day,
                        "command": [
                            "fetch_onedrive_excel",
                            "--date",
                            day,
                            "--country",
                            "CO",
                            "--channel-slug",
                            "whatsapp-uva-co",
                            "--sheet",
                            getattr(settings, "ONEDRIVE_COLOMBIA_SHEET", "Colombia"),
                            "--drive-path",
                            drive_path,
                            "--sync-axis",
                        ],
                    }
                )
            if include_onedrive_ec:
                drive_path = getattr(settings, "ONEDRIVE_ECUADOR_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", "")
                plan.append(
                    {
                        "source": "onedrive-ec",
                        "date": day,
                        "command": [
                            "fetch_onedrive_excel",
                            "--date",
                            day,
                            "--country",
                            "EC",
                            "--channel-slug",
                            "whatsapp-uva-ec",
                            "--sheet",
                            getattr(settings, "ONEDRIVE_ECUADOR_SHEET", "Ecuador"),
                            "--drive-path",
                            drive_path,
                            "--sync-axis",
                        ],
                    }
                )

        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "date_from": start_date.isoformat(),
                        "date_to": end_date.isoformat(),
                        "tasks": plan,
                        "count": len(plan),
                    },
                    indent=2,
                )
            )
            return

        self.stdout.write(
            json.dumps(
                {
                    "status": "starting",
                    "date_from": start_date.isoformat(),
                    "date_to": end_date.isoformat(),
                    "task_count": len(plan),
                },
                indent=2,
            )
        )

        results = []
        errors = []
        total_tasks = len(plan)
        for index, item in enumerate(plan, start=1):
            capture = StringIO()
            try:
                self.stdout.write(f"[{index}/{total_tasks}] {item['source']} {item['date']}")
                call_command(*item["command"], stdout=capture)
                results.append(
                    {
                        "source": item["source"],
                        "date": item["date"],
                        "status": "ok",
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "source": item["source"],
                        "date": item["date"],
                        "status": "error",
                        "error": str(exc),
                    }
                )
                if not options["continue_on_error"]:
                    break

        self.stdout.write(
            json.dumps(
                {
                    "date_from": start_date.isoformat(),
                    "date_to": end_date.isoformat(),
                    "executed": len(results),
                    "errors": errors,
                    "results": results,
                },
                indent=2,
            )
        )
