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
    help = "Sincroniza historico de Helti por rango para ventas y pauta, reutilizando los importadores diarios."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", required=True)
        parser.add_argument("--date-to", required=True)
        parser.add_argument("--uva-sales", action="store_true", help="Incluye WooCommerce y OneDrive de Uva.")
        parser.add_argument("--uva-ads", action="store_true", help="Incluye Meta Ads y Google Ads de Uva.")
        parser.add_argument("--bali", action="store_true", help="Incluye Shopify Bali.")
        parser.add_argument("--websites", action="store_true", help="Incluye diagnostico tecnico de webs activas.")
        parser.add_argument("--marketplace", action="store_true", help="Incluye Mercado Libre y Falabella Marketplace.")
        parser.add_argument("--all", action="store_true", help="Incluye todo lo configurado para Uva y Bali.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--continue-on-error", action="store_true")
        parser.add_argument("--meta-rules", default="docs/mappings/meta-category-rules.example.json")
        parser.add_argument("--google-rules", default="docs/mappings/google-category-rules.example.json")

    def handle(self, *args, **options):
        start_date = date.fromisoformat(options["date_from"])
        end_date = date.fromisoformat(options["date_to"])
        if start_date > end_date:
            raise ValueError("--date-from no puede ser mayor que --date-to.")

        include_uva_sales = options["uva_sales"]
        include_uva_ads = options["uva_ads"]
        include_bali = options["bali"]
        include_websites = options["websites"]
        include_marketplace = options["marketplace"]

        if options["all"] or not any([include_uva_sales, include_uva_ads, include_bali, include_websites, include_marketplace]):
            include_uva_sales = True
            include_uva_ads = True
            include_bali = True
            include_websites = True
            include_marketplace = True

        tasks = []
        for current_date in iter_dates(start_date, end_date):
            day = current_date.isoformat()

            if include_uva_sales:
                if getattr(settings, "WOOCOMMERCE_CO_BASE_URL", ""):
                    tasks.append(
                        {
                            "source": "woocommerce-co",
                            "date": day,
                            "command": ["fetch_woocommerce_sales", "--date", day, "--country", "CO", "--sync-axis"],
                        }
                    )
                if getattr(settings, "WOOCOMMERCE_MX_BASE_URL", ""):
                    tasks.append(
                        {
                            "source": "woocommerce-mx",
                            "date": day,
                            "command": ["fetch_woocommerce_sales", "--date", day, "--country", "MX", "--currency", "MXN", "--sync-axis"],
                        }
                    )
                if getattr(settings, "ONEDRIVE_WHATSAPP_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""):
                    tasks.append(
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
                                getattr(settings, "ONEDRIVE_WHATSAPP_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""),
                                "--sync-axis",
                            ],
                        }
                    )
                if getattr(settings, "ONEDRIVE_ECUADOR_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""):
                    tasks.append(
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
                                getattr(settings, "ONEDRIVE_ECUADOR_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""),
                                "--sync-axis",
                            ],
                        }
                    )

            if include_uva_ads:
                if getattr(settings, "META_CO_ACCOUNT_ID", ""):
                    tasks.append(
                        {
                            "source": "meta-co",
                            "date": day,
                            "command": ["fetch_meta_ads", "--date", day, "--country", "CO", "--rules", options["meta_rules"], "--sync-axis"],
                        }
                    )
                if getattr(settings, "META_MX_ACCOUNT_ID", ""):
                    tasks.append(
                        {
                            "source": "meta-mx",
                            "date": day,
                            "command": ["fetch_meta_ads", "--date", day, "--country", "MX", "--currency", "MXN", "--rules", options["meta_rules"], "--sync-axis"],
                        }
                    )
                if getattr(settings, "META_EC_ACCOUNT_ID", ""):
                    tasks.append(
                        {
                            "source": "meta-ec",
                            "date": day,
                            "command": ["fetch_meta_ads", "--date", day, "--country", "EC", "--currency", "COP", "--rules", options["meta_rules"], "--sync-axis"],
                        }
                    )
                if getattr(settings, "GOOGLE_ADS_CO_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
                    tasks.append(
                        {
                            "source": "google-co",
                            "date": day,
                            "command": ["fetch_google_ads", "--date", day, "--country", "CO", "--rules", options["google_rules"], "--sync-axis"],
                        }
                    )
                if getattr(settings, "GOOGLE_ADS_MX_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
                    tasks.append(
                        {
                            "source": "google-mx",
                            "date": day,
                            "command": ["fetch_google_ads", "--date", day, "--country", "MX", "--currency", "MXN", "--rules", options["google_rules"], "--sync-axis"],
                        }
                    )
                if getattr(settings, "GOOGLE_ADS_EC_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
                    tasks.append(
                        {
                            "source": "google-ec",
                            "date": day,
                            "command": ["fetch_google_ads", "--date", day, "--country", "EC", "--currency", "COP", "--rules", options["google_rules"], "--sync-axis"],
                        }
                    )

            if include_bali and getattr(settings, "SHOPIFY_BALI_SHOP_DOMAIN", ""):
                tasks.append(
                    {
                        "source": "shopify-bali",
                        "date": day,
                        "command": ["fetch_shopify_bali", "--date", day, "--sync-axis"],
                    }
                )
            if include_bali and getattr(settings, "GOOGLE_ADS_BALI_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
                tasks.append(
                    {
                        "source": "google-bali",
                        "date": day,
                        "command": ["fetch_google_ads", "--date", day, "--country", "CO", "--business-unit", "bali", "--sync-axis"],
                    }
                )

            if include_marketplace and ((getattr(settings, "MERCADOLIBRE_CLIENT_ID", "") and getattr(settings, "MERCADOLIBRE_CLIENT_SECRET", "")) or getattr(settings, "MERCADOLIBRE_ACCESS_TOKEN", "")):
                tasks.append({"source": "mercadolibre-marketplace", "date": day, "command": ["sync_mercadolibre_marketplace", "--date", day, "--sales-only"]})
            if include_marketplace and getattr(settings, "FALABELLA_USER_ID", "") and getattr(settings, "FALABELLA_API_KEY", ""):
                tasks.append({"source": "falabella-marketplace", "date": day, "command": ["sync_falabella_marketplace", "--date", day, "--sales-only"]})

        if include_uva_sales and getattr(settings, "ONEDRIVE_SHARED_COMFAMA_FILE_PATH", ""):
            tasks.append(
                {
                    "source": "onedrive-comfama-sales",
                    "date": f"{start_date.isoformat()}..{end_date.isoformat()}",
                    "command": ["fetch_onedrive_comfama_sales"],
                }
            )


        if (include_uva_ads or include_bali) and getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
            tasks.append(
                {
                    "source": "onedrive-google-ads-workbook",
                    "date": f"{start_date.isoformat()}..{end_date.isoformat()}",
                    "command": ["fetch_onedrive_google_ads", "--sync-axis"],
                }
            )

        if include_uva_ads and getattr(settings, "ONEDRIVE_AWARENESS_FILE_PATH", ""):
            tasks.append(
                {
                    "source": "onedrive-awareness-awn",
                    "date": f"{start_date.isoformat()}..{end_date.isoformat()}",
                    "command": ["fetch_onedrive_awn_followers", "--end-date", end_date.isoformat()],
                }
            )

        if include_websites:
            tasks.append(
                {
                    "source": "websites-health",
                    "date": end_date.isoformat(),
                    "command": ["sync_websites_health"],
                }
            )

        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "date_from": start_date.isoformat(),
                        "date_to": end_date.isoformat(),
                        "task_count": len(tasks),
                        "tasks": tasks,
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
                    "task_count": len(tasks),
                },
                indent=2,
            )
        )

        results = []
        errors = []
        total_tasks = len(tasks)
        for index, task in enumerate(tasks, start=1):
            capture = StringIO()
            try:
                self.stdout.write(
                    f"[{index}/{total_tasks}] {task['source']} {task['date']}",
                    ending="\n",
                )
                call_command(*task["command"], stdout=capture)
                results.append({"source": task["source"], "date": task["date"], "status": "ok"})
            except Exception as exc:
                errors.append({"source": task["source"], "date": task["date"], "status": "error", "error": str(exc)})
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
