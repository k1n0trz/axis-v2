import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction

from reports.integrations.axis_sync import AxisSyncService
from reports.integrations.clients import ShopifyClient
from reports.integrations.schema import BaliMetricRecord
from reports.models import BaliDailyMetric, BaliWebProductDailyMetric


class Command(BaseCommand):
    help = "Consulta Shopify Bali y construye la metrica diaria web base usando sesiones como trafico oficial."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True)
        parser.add_argument("--shop-domain", default="")
        parser.add_argument("--access-token", default="")
        parser.add_argument("--api-version", default="")
        parser.add_argument("--sessions", default="0", help="Sesiones del dia si se tienen desde otra fuente.")
        parser.add_argument("--visits", default="", help="Alias legacy de sessions. Se mantiene por compatibilidad.")
        parser.add_argument("--google-spend", default=None, help="Gasto de Google Ads del dia para Bali si ya se conoce.")
        parser.add_argument("--google-orders", default=None, help="Pedidos atribuidos a Google Ads si ya se conocen.")
        parser.add_argument("--whatsapp-conversations", default=None, help="Conversaciones de WhatsApp si ya se conocen.")
        parser.add_argument("--cpa", default=None, help="CPA global si ya se conoce.")
        parser.add_argument(
            "--allow-orders-fallback",
            action="store_true",
            help="Usa ordenes REST si Analytics no esta disponible. No coincide con las metricas oficiales de Shopify.",
        )
        parser.add_argument("--sync-axis", action="store_true")

    def handle(self, *args, **options):
        shop_domain = options["shop_domain"] or getattr(settings, "SHOPIFY_BALI_SHOP_DOMAIN", "")
        access_token = options["access_token"] or getattr(settings, "SHOPIFY_BALI_ACCESS_TOKEN", "")
        api_version = options["api_version"] or getattr(settings, "SHOPIFY_BALI_API_VERSION", "2025-10")
        if not shop_domain or not access_token:
            raise CommandError("Faltan SHOPIFY_BALI_SHOP_DOMAIN y/o SHOPIFY_BALI_ACCESS_TOKEN.")
        normalized_domain = str(shop_domain).strip().replace("https://", "").replace("http://", "").strip("/")
        if not normalized_domain.endswith(".myshopify.com"):
            raise CommandError(
                "SHOPIFY_BALI_SHOP_DOMAIN debe ser el dominio permanente de Shopify terminado en .myshopify.com, "
                "no el dominio publico de la tienda."
            )

        target_date = date.fromisoformat(options["date"])
        client = ShopifyClient(shop_domain, access_token, api_version=api_version)

        web_sales_amount = Decimal("0")
        web_order_count = 0
        orders = []
        session_seed = options["sessions"] if options["sessions"] not in (None, "") else (options["visits"] or "0")
        sessions = int(Decimal(str(session_seed)))
        warning = "Shopify no entrego sesiones en este comando. Ese campo debe completarse desde otra fuente mientras se define la fuente oficial."
        analytics_source = "shopifyql"
        analytics_error = ""
        product_analytics_error = ""
        products_synced = 0

        try:
            shopifyql = (
                f"FROM sales, sessions "
                f"SHOW day, total_sales, orders, sessions "
                f"GROUP BY day "
                f"SINCE {target_date.isoformat()} UNTIL {target_date.isoformat()}"
            )
            table = client.shopifyql_query(shopifyql)
            rows = table.get("rows") or []
            if rows:
                row = rows[0]
                web_sales_amount = Decimal(str(row.get("total_sales") or "0"))
                web_order_count = int(Decimal(str(row.get("orders") or "0")))
                sessions = int(Decimal(str(row.get("sessions") or "0")))
            warning = ""
        except Exception as exc:
            analytics_error = str(exc)
            if not options["allow_orders_fallback"]:
                raise CommandError(
                    "Shopify Analytics no esta disponible; no se guardaron ventas web de Bali. "
                    "Otorga al token los permisos requeridos por shopifyqlQuery (incluido read_reports "
                    "y el acceso a datos protegidos indicado por Shopify). Usa --allow-orders-fallback "
                    "solo si aceptas que las ordenes REST no coinciden con el reporte de Analytics."
                ) from exc
            analytics_source = "orders-api"

        if analytics_source != "shopifyql":
            orders = client.get_orders_for_day(target_date)
            web_sales_amount = Decimal("0")
            web_order_count = 0
            for order in orders:
                web_sales_amount += Decimal(str(order.get("current_total_price") or order.get("total_price") or "0"))
                web_order_count += 1
            warning = (
                "Se uso la API de ordenes como aproximacion porque Shopify Analytics no estuvo disponible. "
                "Ventas, pedidos y sesiones pueden no coincidir con el reporte oficial."
            )

        existing_metric = (
            BaliDailyMetric.objects.filter(
                business_unit__slug="bali",
                country__code="CO",
                metric_date=target_date,
            )
            .order_by("-updated_at")
            .first()
        )
        google_spend_amount = self._decimal_option(options["google_spend"], existing_metric.google_spend_amount if existing_metric else Decimal("0"))
        google_attributed_orders = self._int_option(options["google_orders"], existing_metric.google_attributed_orders if existing_metric else 0)
        whatsapp_conversations = self._int_option(options["whatsapp_conversations"], existing_metric.whatsapp_conversations if existing_metric else 0)
        cpa = self._decimal_option(options["cpa"], existing_metric.cpa if existing_metric else Decimal("0"))
        preserved_ads = existing_metric and any(
            options[name] in (None, "")
            for name in ("google_spend", "google_orders", "whatsapp_conversations", "cpa")
        )
        source_file = analytics_source
        if preserved_ads and existing_metric.source_file:
            source_file = self._merge_source_files(existing_metric.source_file, analytics_source)

        record = BaliMetricRecord(
            business_unit_slug="bali",
            country_code="CO",
            metric_date=target_date,
            sessions=sessions,
            web_sales_amount=web_sales_amount,
            web_order_count=web_order_count,
            google_spend_amount=google_spend_amount,
            google_attributed_orders=google_attributed_orders,
            whatsapp_conversations=whatsapp_conversations,
            cpa=cpa,
            source_file=source_file,
            notes=(
                "Importacion Bali desde Shopify Analytics usando sesiones como metrica de trafico. "
                "Google Ads y WhatsApp se preservan si ya fueron importados."
                if analytics_source == "shopifyql"
                else "Importacion provisional Bali desde ordenes Shopify REST; no equivale al reporte Analytics. "
                "Google Ads y WhatsApp se preservan si ya fueron importados."
            ),
        )

        if options["sync_axis"]:
            AxisSyncService().sync_bali_metrics([record])
            if analytics_source == "shopifyql":
                try:
                    products_synced = self._sync_product_metrics(client, target_date)
                except Exception as exc:
                    product_analytics_error = str(exc)
                    warning = (
                        (warning + " " if warning else "")
                        + "No fue posible actualizar el detalle de productos Shopify para esta fecha."
                    )

        payload = {
            "metric": record.to_dict(),
            "sessions": sessions,
            "orders_fetched": len(orders),
            "warning": warning,
            "analytics_source": analytics_source,
            "analytics_error": analytics_error,
            "products_synced": products_synced,
            "product_analytics_error": product_analytics_error,
            "api_version": api_version,
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))

    def _sync_product_metrics(self, client, target_date):
        shopifyql = (
            "FROM sales "
            "SHOW product_title, net_items_sold, gross_sales, discounts, returns, net_sales, total_sales "
            "GROUP BY product_title "
            f"SINCE {target_date.isoformat()} UNTIL {target_date.isoformat()} "
            "ORDER BY net_items_sold DESC, total_sales DESC "
            "LIMIT 1000"
        )
        rows = client.shopifyql_query(shopifyql).get("rows") or []
        product_images = client.product_images_by_title()
        daily_metric = BaliDailyMetric.objects.select_related("business_unit", "country").get(
            business_unit__slug="bali",
            country__code="CO",
            metric_date=target_date,
        )
        product_metrics = []
        for row in rows:
            product_title = str(row.get("product_title") or "").strip()
            if not product_title:
                continue
            product_metrics.append(
                BaliWebProductDailyMetric(
                    business_unit=daily_metric.business_unit,
                    country=daily_metric.country,
                    metric_date=target_date,
                    product_title=product_title[:255],
                    net_items_sold=int(Decimal(str(row.get("net_items_sold") or "0"))),
                    gross_sales=Decimal(str(row.get("gross_sales") or "0")),
                    discounts=Decimal(str(row.get("discounts") or "0")),
                    returns=Decimal(str(row.get("returns") or "0")),
                    net_sales=Decimal(str(row.get("net_sales") or "0")),
                    total_sales=Decimal(str(row.get("total_sales") or "0")),
                    product_image_url=product_images.get(product_title.casefold(), ""),
                    source_file="shopifyql",
                )
            )
        with transaction.atomic():
            BaliWebProductDailyMetric.objects.filter(
                business_unit=daily_metric.business_unit,
                country=daily_metric.country,
                metric_date=target_date,
            ).delete()
            BaliWebProductDailyMetric.objects.bulk_create(product_metrics)
        return len(product_metrics)

    def _decimal_option(self, raw_value, fallback):
        if raw_value in (None, ""):
            return fallback
        return Decimal(str(raw_value))

    def _int_option(self, raw_value, fallback):
        if raw_value in (None, ""):
            return fallback
        return int(Decimal(str(raw_value)))

    def _merge_source_files(self, existing_source, analytics_source):
        parts = [
            part.strip()
            for part in str(existing_source or "").split(";")
            if part.strip() and part.strip().lower() not in {"orders-api", "shopifyql"}
        ]
        parts.append(analytics_source)
        return "; ".join(dict.fromkeys(parts))
