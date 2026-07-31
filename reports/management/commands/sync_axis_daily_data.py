import json
from datetime import date, timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone




class Command(BaseCommand):
    help = "Orquesta las fuentes externas configuradas para un dia y sincroniza Helti automaticamente."

    def add_arguments(self, parser):
        parser.add_argument("--date", default="yesterday")
        parser.add_argument("--lookback-days", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--continue-on-error", action="store_true")
        parser.add_argument("--meta-rules", default="docs/mappings/meta-category-rules.example.json")
        parser.add_argument("--google-rules", default="docs/mappings/google-category-rules.json")
        parser.add_argument(
            "--onedrive-sales-lookback-days",
            type=int,
            default=getattr(settings, "ONEDRIVE_SALES_LOOKBACK_DAYS", 3),
            help="Dias recientes que se reintentan para ventas OneDrive de Colombia/Ecuador.",
        )

    def handle(self, *args, **options):
        target_date = self._resolve_target_date(options["date"])
        lookback_days = max(1, int(options["lookback_days"] or 1))
        dates = [target_date - timedelta(days=offset) for offset in range(lookback_days - 1, -1, -1)]
        tasks = self._build_tasks_for_dates(dates, options)

        if options["dry_run"]:
            self.stdout.write(
                json.dumps(
                    {
                        "date": target_date.isoformat(),
                        "date_from": dates[0].isoformat(),
                        "date_to": dates[-1].isoformat(),
                        "lookback_days": lookback_days,
                        "dry_run": True,
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
                    "date": target_date.isoformat(),
                    "date_from": dates[0].isoformat(),
                    "date_to": dates[-1].isoformat(),
                    "lookback_days": lookback_days,
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
                self.stdout.write(f"[{index}/{total_tasks}] {task['name']}")
                call_command(*task["command"], stdout=capture)
                results.append({"name": task["name"], "status": "ok"})
            except Exception as exc:
                errors.append({"name": task["name"], "status": "error", "error": str(exc)})
                if not options["continue_on_error"]:
                    break

        self.stdout.write(
            json.dumps(
                {
                    "date": target_date.isoformat(),
                    "date_from": dates[0].isoformat(),
                    "date_to": dates[-1].isoformat(),
                    "lookback_days": lookback_days,
                    "executed": len(results),
                    "errors": errors,
                    "results": results,
                },
                indent=2,
            )
        )

    def _build_tasks_for_dates(self, dates, options):
        tasks = []
        global_seen = set()
        for target_date in dates:
            for task in self._build_tasks(target_date, options, include_onedrive_sales=False):
                if "--date" not in task["command"]:
                    key = tuple(task["command"])
                    if key in global_seen:
                        continue
                    global_seen.add(key)
                tasks.append(task)
        onedrive_lookback = max(1, int(options.get("onedrive_sales_lookback_days") or 1))
        onedrive_end = dates[-1]
        onedrive_start = onedrive_end - timedelta(days=onedrive_lookback - 1)
        tasks.extend(self._build_onedrive_sales_tasks(onedrive_start, onedrive_end))
        return tasks

    def _build_onedrive_sales_tasks(self, target_date, end_date=None):
        if end_date and end_date != target_date:
            date_args = ["--date-from", target_date.isoformat(), "--date-to", end_date.isoformat()]
            date_label = f"{target_date.isoformat()}..{end_date.isoformat()}"
        else:
            date_args = ["--date", target_date.isoformat()]
            date_label = target_date.isoformat()
        tasks = []
        if getattr(settings, "ONEDRIVE_WHATSAPP_FILE_PATH", "") or getattr(settings, "ONEDRIVE_SHARED_SALES_FILE_PATH", ""):
            tasks.append(
                {
                    "name": f"OneDrive WhatsApp Colombia {date_label}",
                    "command": [
                        "fetch_onedrive_excel",
                        *date_args,
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
                    "name": f"OneDrive Ecuador {date_label}",
                    "command": [
                        "fetch_onedrive_excel",
                        *date_args,
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
        return tasks

    def _build_tasks(self, target_date, options, include_onedrive_sales=True):
        day = target_date.isoformat()
        tasks = []

        if getattr(settings, "WOOCOMMERCE_CO_BASE_URL", ""):
            tasks.append(
                {
                    "name": "WooCommerce Colombia",
                    "command": ["fetch_woocommerce_sales", "--date", day, "--country", "CO", "--sync-axis"],
                }
            )
        if getattr(settings, "WOOCOMMERCE_MX_BASE_URL", ""):
            tasks.append(
                {
                    "name": "WooCommerce Mexico",
                    "command": ["fetch_woocommerce_sales", "--date", day, "--country", "MX", "--currency", "MXN", "--sync-axis"],
                }
            )
        if include_onedrive_sales:
            tasks.extend(self._build_onedrive_sales_tasks(target_date))
        if getattr(settings, "ONEDRIVE_SHARED_COMFAMA_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "OneDrive Ventas Comfama",
                    "command": ["fetch_onedrive_comfama_sales"],
                }
            )
        if getattr(settings, "META_CO_ACCOUNT_ID", ""):
            tasks.append(
                {
                    "name": "Meta Ads Colombia",
                    "command": ["fetch_meta_ads", "--date", day, "--country", "CO", "--rules", options["meta_rules"], "--sync-axis"],
                }
            )
        if getattr(settings, "META_MX_ACCOUNT_ID", ""):
            tasks.append(
                {
                    "name": "Meta Ads Mexico",
                    "command": ["fetch_meta_ads", "--date", day, "--country", "MX", "--currency", "MXN", "--rules", options["meta_rules"], "--sync-axis"],
                }
            )
        if getattr(settings, "META_EC_ACCOUNT_ID", ""):
            tasks.append(
                {
                    "name": "Meta Ads Ecuador",
                    "command": ["fetch_meta_ads", "--date", day, "--country", "EC", "--currency", "COP", "--rules", options["meta_rules"], "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_CO_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "Google Ads Colombia",
                    "command": ["fetch_google_ads", "--date", day, "--country", "CO", "--rules", options["google_rules"], "--count-unmapped-spend", "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_MX_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "Google Ads Mexico",
                    "command": ["fetch_google_ads", "--date", day, "--country", "MX", "--currency", "MXN", "--rules", options["google_rules"], "--count-unmapped-spend", "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_EC_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "Google Ads Ecuador",
                    "command": ["fetch_google_ads", "--date", day, "--country", "EC", "--currency", "COP", "--rules", options["google_rules"], "--count-unmapped-spend", "--sync-axis"],
                }
            )
        if getattr(settings, "SHOPIFY_BALI_SHOP_DOMAIN", ""):
            tasks.append(
                {
                    "name": "Shopify Bali",
                    "command": ["fetch_shopify_bali", "--date", day, "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_BALI_CUSTOMER_ID", "") and not getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "Google Ads Bali",
                    "command": ["fetch_google_ads", "--date", day, "--country", "CO", "--business-unit", "bali", "--sync-axis"],
                }
            )
        if getattr(settings, "ONEDRIVE_GOOGLE_ADS_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "OneDrive Google Ads Workbook",
                    "command": ["fetch_onedrive_google_ads", "--sync-axis"],
                }
            )
        if (getattr(settings, "MERCADOLIBRE_CLIENT_ID", "") and getattr(settings, "MERCADOLIBRE_CLIENT_SECRET", "")) or getattr(settings, "MERCADOLIBRE_ACCESS_TOKEN", ""):
            tasks.append(
                {
                    "name": "Mercado Libre Marketplace",
                    "command": ["sync_mercadolibre_marketplace", "--date", day],
                }
            )
        if getattr(settings, "FALABELLA_USER_ID", "") and getattr(settings, "FALABELLA_API_KEY", ""):
            tasks.append(
                {
                    "name": "Falabella Marketplace",
                    "command": ["sync_falabella_marketplace", "--date", day],
                }
            )

        if getattr(settings, "ONEDRIVE_AWARENESS_FILE_PATH", ""):
            tasks.append(
                {
                    "name": "OneDrive Awareness Awn",
                    "command": ["fetch_onedrive_awn_followers"],
                }
            )
        if all(
            [
                getattr(settings, "META_REPORTS_IMAP_HOST", ""),
                getattr(settings, "META_REPORTS_IMAP_USERNAME", ""),
                getattr(settings, "META_REPORTS_IMAP_PASSWORD", ""),
            ]
        ):
            tasks.append(
                {
                    "name": "Meta Followers Email Reports",
                    "command": ["fetch_meta_followers_email_reports", "--all"],
                }
            )

        return tasks

    def _resolve_target_date(self, raw_value):
        value = str(raw_value or "").strip().lower()
        today = timezone.localdate()
        if value in {"", "today", "hoy"}:
            return today
        if value in {"yesterday", "ayer"}:
            return today - timedelta(days=1)
        return date.fromisoformat(str(raw_value))