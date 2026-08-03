import json
import re
from datetime import date, timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from reports.integrations.run_log import track_run




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
            "--only",
            default="",
            help=(
                "Corre solo las fuentes cuyo nombre contenga este texto (varias separadas "
                "por ;). Para rellenar una fuente sin arrastrar Meta y Google de vuelta."
            ),
        )
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
        tasks = self._filter_tasks(tasks, options["only"])
        if options["only"] and not tasks:
            raise CommandError(
                f"Ninguna fuente coincide con --only '{options['only']}'. "
                "Corre con --dry-run para ver los nombres disponibles."
            )

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
            source, task_date = self._source_and_date(task)
            self.stdout.write(f"[{index}/{total_tasks}] {task['name']}")
            try:
                # Cada fuente deja su propia fila en la bitacora. Sin esto, cuando
                # un dato no aparecia en el tablero no habia forma de saber si el
                # job no corrio, corrio y fallo, o la fuente venia vacia.
                with track_run(source, command=task["command"][0], target_date=task_date) as run:
                    call_command(*task["command"], stdout=capture)
                    texto = capture.getvalue()
                    run.payload = self._run_payload(texto)
                    run.summary = self._run_summary(task["name"], run.payload)
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


    # La fecha al final del nombre es del dia procesado, no de la fuente: se saca
    # del slug para que las corridas de distintos dias se agrupen bajo la misma
    # fuente. Las tareas de OneDrive traen un rango ("... 2026-07-28..2026-07-30"),
    # asi que hay que quitar las dos fechas y quedarse con la ultima.
    DATE_IN_NAME = re.compile(r"\s+(\d{4}-\d{2}-\d{2})(?:\.\.(\d{4}-\d{2}-\d{2}))?$")

    def _source_and_date(self, task):
        name = task["name"]
        match = self.DATE_IN_NAME.search(name)
        task_date = None
        if match:
            # Con rango, la fecha que interesa es la ultima del rango.
            task_date = date.fromisoformat(match.group(2) or match.group(1))
            name = name[: match.start()]
        if task_date is None:
            task_date = self._date_from_command(task["command"])
        return slugify(name).replace("-", "_"), task_date

    def _date_from_command(self, command):
        candidates = []
        for index, argument in enumerate(command):
            texto = str(argument)
            if texto.startswith(("--date=", "--date-to=", "--date-from=")):
                candidates.append(texto.split("=", 1)[1])
            elif texto in ("--date", "--date-to", "--date-from") and index + 1 < len(command):
                candidates.append(str(command[index + 1]))
        for candidate in reversed(candidates):
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    def _run_payload(self, output):
        """Resumen del payload del comando, no el payload completo.

        La salida de estos comandos puede traer cientos de filas; la bitacora es
        para diagnosticar, no un respaldo. Antes esta salida se descartaba entera
        cuando el comando terminaba bien.
        """
        try:
            data = json.loads(output)
        except ValueError:
            return {"output": output[-1200:]}
        if isinstance(data, list):
            return {"items": len(data)}
        if not isinstance(data, dict):
            return {"output": str(data)[:200]}

        payload = {}
        for key, value in data.items():
            if isinstance(value, (int, float, bool)) or value is None:
                payload[key] = value
            elif isinstance(value, str):
                payload[key] = value[:200]
            elif isinstance(value, list):
                payload[f"{key}_count"] = len(value)
        # Lo que el auditor de precios haya encontrado tiene que verse aqui.
        sospechosas = data.get("suspicious_unit_prices") or []
        if sospechosas:
            payload["suspicious_unit_prices"] = [str(item.get("message", ""))[:200] for item in sospechosas[:5]]
        canal = data.get("channel_sale") or {}
        if isinstance(canal, dict) and canal:
            payload["channel_sale_amount"] = str(canal.get("sales_amount", ""))
            payload["channel_sale_orders"] = canal.get("order_count")
        gasto = data.get("daily_spend") or {}
        if isinstance(gasto, dict) and gasto:
            payload["spend_amount"] = str(gasto.get("spend_amount", ""))
        return payload

    def _run_summary(self, task_name, payload):
        partes = []
        for clave in ("channel_sale_amount", "channel_sale_orders", "spend_amount", "checked", "created", "updated", "items"):
            if payload.get(clave) not in (None, "", 0):
                partes.append(f"{clave}={payload[clave]}")
        for clave, valor in payload.items():
            if clave.endswith("_count") and valor:
                partes.append(f"{clave}={valor}")
        if payload.get("suspicious_unit_prices"):
            partes.append(f"VALOR sospechoso en {len(payload['suspicious_unit_prices'])} filas")
        if not partes:
            partes.append("sin novedades")
        return f"{task_name}: " + ", ".join(partes[:8])

    def _filter_tasks(self, tasks, only):
        """Deja solo las fuentes que pidio --only. Sin --only no filtra nada."""
        patrones = [p.strip().lower() for p in str(only or "").split(";") if p.strip()]
        if not patrones:
            return tasks
        return [t for t in tasks if any(p in t["name"].lower() for p in patrones)]

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
        if getattr(settings, "WOOCOMMERCE_DISTRISEX_BASE_URL", ""):
            # DistriSex vende en Colombia pero con su propia tienda, asi que se
            # elige por --store y no por pais. Sin mapa de categorias su catalogo
            # mayorista generaria cientos de categorias basura por dia, de ahi
            # --skip-category-sales.
            tasks.append(
                {
                    "name": "WooCommerce DistriSex",
                    "command": [
                        "fetch_woocommerce_sales", "--date", day, "--country", "CO",
                        "--store", "DISTRISEX", "--business-unit", "distrisex",
                        "--channel-slug", "ecommerce-distrisex", "--skip-category-sales", "--sync-axis",
                    ],
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
        # Google Ads entra SIEMPRE por API. Antes estas cuatro tareas se apagaban si
        # existia ONEDRIVE_GOOGLE_ADS_FILE_PATH, y en produccion esa variable apuntaba
        # a axis/google-ads.xlsx, un archivo que no existe: OneDrive responde 404. O
        # sea que la pauta de Google de Uva y Bali no entraba por ningun lado, y la
        # tarea del workbook fallaba todos los dias. En Excel solo hay ventas por
        # WhatsApp (Uva Ecuador, Uva Colombia y Comfama), nunca Google Ads.
        if getattr(settings, "GOOGLE_ADS_CO_CUSTOMER_ID", ""):
            tasks.append(
                {
                    "name": "Google Ads Colombia",
                    "command": ["fetch_google_ads", "--date", day, "--country", "CO", "--rules", options["google_rules"], "--count-unmapped-spend", "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_MX_CUSTOMER_ID", ""):
            tasks.append(
                {
                    "name": "Google Ads Mexico",
                    "command": ["fetch_google_ads", "--date", day, "--country", "MX", "--currency", "MXN", "--rules", options["google_rules"], "--count-unmapped-spend", "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_EC_CUSTOMER_ID", ""):
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
        if getattr(settings, "GOOGLE_ADS_BALI_CUSTOMER_ID", ""):
            tasks.append(
                {
                    "name": "Google Ads Bali",
                    "command": ["fetch_google_ads", "--date", day, "--country", "CO", "--business-unit", "bali", "--sync-axis"],
                }
            )
        if getattr(settings, "GOOGLE_ADS_DISTRISEX_CUSTOMER_ID", ""):
            # A diferencia de Uva y Bali, DistriSex NO se condiciona al workbook de
            # OneDrive: ese archivo lo llena una persona y no incluye esta cuenta,
            # que era invisible para Axis hasta que se dio el permiso en el MCC. Sin
            # esto su inversion no llegaria nunca. No hay riesgo de duplicar: la
            # restriccion unica de DailyAdSpend es (marca, pais, plataforma, fecha),
            # asi que si el workbook algun dia la trajera, se sobreescribe.
            tasks.append(
                {
                    "name": "Google Ads DistriSex",
                    "command": [
                        "fetch_google_ads", "--date", day, "--country", "CO",
                        "--business-unit", "distrisex", "--count-unmapped-spend", "--sync-axis",
                    ],
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
        if getattr(settings, "DEEPSEEK_API_KEY", ""):
            # Sin --date a proposito: la destilacion no es por fecha, y
            # `_build_tasks_for_dates` deduplica los comandos sin fecha, asi que en una
            # corrida de varios dias se ejecuta una sola vez.
            tasks.append(
                {
                    "name": "IA memorias",
                    "command": ["distill_ai_memories"],
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