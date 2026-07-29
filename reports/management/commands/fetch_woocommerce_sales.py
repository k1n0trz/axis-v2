import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from reports.integrations.axis_sync import AxisSyncService
from reports.integrations.clients import ExchangeRateClient, WooCommerceClient, load_json_mapping
from reports.integrations.schema import CategorySaleRecord, ChannelSaleRecord
from reports.models import BusinessUnit, Channel, Country, DailyProductCategorySale
from reports.services.sales_dashboard import category_slug_from_product_name, uva_category_slug_from_product_name, uva_exchange_rate_for_country

MONEY_QUANT = Decimal("0.01")


def env_prefix(country_code):
    return f"WOOCOMMERCE_{country_code.upper()}"


def display_name_for_category(slug):
    labels = {
        "copa-menstrual": "Copa Menstrual",
        "disco-menstrual": "Disco Menstrual",
        "dilatadores-vaginales": "Dilatadores Vaginales",
        "higiene-intima": "Higiene Intima",
        "kits": "Kits",
        "lubricantes": "Lubricantes",
        "panties-menstruales": "Panties Menstruales",
        "cubrepezones": "Cubrepezones",
    }
    return labels.get(slug, slug.replace("-", " ").title())


class Command(BaseCommand):
    help = "Consulta WooCommerce y consolida ventas diarias por producto/categoria."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True)
        parser.add_argument("--country", default="CO")
        parser.add_argument("--business-unit", default="uva")
        parser.add_argument("--channel-slug", default="ecommerce-uva")
        parser.add_argument("--base-url", default="")
        parser.add_argument("--consumer-key", default="")
        parser.add_argument("--consumer-secret", default="")
        parser.add_argument("--currency", default="COP")
        parser.add_argument("--exchange-rate", default="1")
        parser.add_argument("--category-map", default="")
        parser.add_argument("--timezone", default=getattr(settings, "TIME_ZONE", "America/Bogota"))
        parser.add_argument("--statuses", default="completed,on-hold,processing")
        parser.add_argument("--sales-mode", choices=("net", "gross"), default="net")
        parser.add_argument("--debug-orders", action="store_true")
        parser.add_argument("--sync-axis", action="store_true")

    def handle(self, *args, **options):
        target_date = options["date"]
        prefix = env_prefix(options["country"])
        base_url = options["base_url"] or getattr(settings, f"{prefix}_BASE_URL", "")
        consumer_key = options["consumer_key"] or getattr(settings, f"{prefix}_CONSUMER_KEY", "")
        consumer_secret = options["consumer_secret"] or getattr(settings, f"{prefix}_CONSUMER_SECRET", "")
        if not all([base_url, consumer_key, consumer_secret]):
            raise CommandError("Faltan credenciales/base URL de WooCommerce.")

        category_map = load_json_mapping(options["category_map"])
        currency = options["currency"].upper()
        rate = self._resolve_exchange_rate(options["country"].upper(), currency, Decimal(str(options["exchange_rate"])), target_date)
        client = WooCommerceClient(base_url, consumer_key, consumer_secret)
        daily = {"sales_amount": Decimal("0"), "orders": 0, "units": 0}
        by_category = defaultdict(lambda: {"sales": Decimal("0"), "original": Decimal("0"), "qty": 0, "products": set()})
        debug_orders = []
        skipped_products = defaultdict(lambda: {"qty": 0, "original": Decimal("0")})
        report_payload = {}
        tz = ZoneInfo(options["timezone"])
        day_start = datetime.combine(datetime.fromisoformat(target_date).date(), time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        after = day_start.isoformat()
        before = day_end.isoformat()
        statuses = [item.strip() for item in options["statuses"].split(",") if item.strip()]
        is_uva_import = str(options["business_unit"]).strip().lower() == "uva"

        for order in client.iter_orders_for_day(
            __import__("datetime").date.fromisoformat(target_date),
            statuses=statuses,
            after=after,
            before=before,
        ):
            gross_total = Decimal(str(order.get("total") or "0"))
            shipping_total = Decimal(str(order.get("shipping_total") or "0"))
            net_total = gross_total - shipping_total
            order_sales_value = Decimal("0")
            order_units = 0
            if options["debug_orders"]:
                debug_orders.append(
                    {
                        "id": order.get("id"),
                        "status": order.get("status"),
                        "date_created": order.get("date_created"),
                        "date_created_gmt": order.get("date_created_gmt"),
                        "gross_total": str(gross_total),
                        "net_total": str(net_total),
                        "shipping_total": order.get("shipping_total"),
                        "discount_total": order.get("discount_total"),
                    }
                )
            for item in order.get("line_items", []):
                product_name = str(item.get("name") or "").strip()
                if not product_name:
                    continue
                qty = int(item.get("quantity") or 0)
                line_total = Decimal(str((item.get("subtotal") if options["sales_mode"] == "gross" else item.get("total")) or "0"))
                slug = (
                    uva_category_slug_from_product_name(product_name, category_map)
                    if is_uva_import
                    else (category_map.get(product_name) or category_slug_from_product_name(product_name))
                )
                if not slug:
                    skipped_products[product_name]["qty"] += qty
                    skipped_products[product_name]["original"] += line_total
                    continue
                by_category[slug]["sales"] += line_total * rate
                by_category[slug]["original"] += line_total
                by_category[slug]["qty"] += qty
                by_category[slug]["products"].add(product_name)
                order_sales_value += line_total
                order_units += qty
            if order_sales_value or order_units:
                daily["sales_amount"] += order_sales_value * rate
                daily["orders"] += 1
                daily["units"] += order_units

        try:
            report_payload = client.get_sales_report_for_day(__import__("datetime").date.fromisoformat(target_date))
        except Exception:
            report_payload = {}

        official_sales_amount = self._official_report_amount(report_payload, daily["sales_amount"], rate)
        official_order_count = self._official_report_int(report_payload, "total_orders", daily["orders"])
        official_units = self._official_report_int(report_payload, "total_items", daily["units"])
        residual_original = self._residual_original_amount(official_sales_amount, by_category, rate)
        if residual_original:
            by_category["otros-uva"]["sales"] += residual_original * rate
            by_category["otros-uva"]["original"] += residual_original
            by_category["otros-uva"]["products"].add("Ajuste reporte WooCommerce")

        channel_record = ChannelSaleRecord(
            business_unit_slug=options["business_unit"],
            country_code=options["country"].upper(),
            channel_slug=options["channel_slug"],
            sale_date=__import__("datetime").date.fromisoformat(target_date),
            sales_amount=official_sales_amount,
            order_count=official_order_count,
            units=official_units,
            source_file="woocommerce-api",
            notes=self._build_channel_note(options["country"].upper(), currency, rate),
        )
        category_records = [
            CategorySaleRecord(
                business_unit_slug=options["business_unit"],
                country_code=options["country"].upper(),
                channel_slug=options["channel_slug"],
                category_slug=slug,
                category_name=display_name_for_category(slug),
                sale_date=__import__("datetime").date.fromisoformat(target_date),
                sales_amount=(values["original"] * rate).quantize(MONEY_QUANT),
                original_amount=values["original"].quantize(MONEY_QUANT),
                original_currency=currency,
                exchange_rate=rate,
                quantity=values["qty"],
                source_file="woocommerce-api",
                notes="Productos fuente: " + ", ".join(sorted(values["products"])),
            )
            for slug, values in sorted(by_category.items())
        ]

        if options["sync_axis"]:
            sync = AxisSyncService()
            sync.sync_channel_sales([channel_record])
            self._delete_existing_api_category_sales(options, channel_record.sale_date)
            sync.sync_category_sales(category_records)

        self.stdout.write(
            json.dumps(
                {
                    "channel_sale": channel_record.to_dict(),
                    "category_sales": [item.to_dict() for item in category_records],
                    "debug": {
                        "timezone": options["timezone"],
                        "after": after,
                        "before": before,
                        "statuses": statuses,
                        "sales_mode": options["sales_mode"],
                        "currency": currency,
                        "exchange_rate": str(rate),
                        "report_sales": report_payload,
                        "skipped_products": self._skipped_products_payload(skipped_products),
                        "orders": debug_orders,
                    } if options["debug_orders"] else {
                        "timezone": options["timezone"],
                        "after": after,
                        "before": before,
                        "statuses": statuses,
                        "sales_mode": options["sales_mode"],
                        "currency": currency,
                        "exchange_rate": str(rate),
                        "report_sales": report_payload,
                        "skipped_products": self._skipped_products_payload(skipped_products),
                    },
                },
                indent=2,
                default=str,
            )
        )

    def _resolve_exchange_rate(self, country_code, currency, explicit_rate, target_date):
        if currency == "COP":
            return Decimal("1")
        fixed_rate = uva_exchange_rate_for_country(country_code, currency)
        if fixed_rate != Decimal("1"):
            return fixed_rate
        if explicit_rate != Decimal("1"):
            return explicit_rate

        fx_url = getattr(settings, "EXCHANGE_RATE_API_URL", "")
        if not fx_url:
            raise CommandError(
                f"No se puede convertir {currency} a COP automaticamente porque falta EXCHANGE_RATE_API_URL."
            )

        fx = ExchangeRateClient(
            fx_url,
            api_key=getattr(settings, "EXCHANGE_RATE_API_KEY", ""),
        )
        try:
            return fx.convert(currency, "COP", Decimal("1"), target_date=datetime.fromisoformat(target_date).date())
        except Exception as exc:
            raise CommandError(
                f"No fue posible convertir {currency} a COP para {target_date}: {exc}"
            ) from exc

    def _build_channel_note(self, country_code, currency, rate):
        if currency == "COP":
            return f"Importado desde WooCommerce {country_code}."
        return f"Importado desde WooCommerce {country_code}. Convertido de {currency} a COP con tasa {rate}."

    def _official_report_amount(self, report_payload, fallback_amount, rate):
        for key in ("net_sales", "total_sales"):
            value = report_payload.get(key) if isinstance(report_payload, dict) else None
            if value not in (None, ""):
                return Decimal(str(value)) * rate
        return fallback_amount

    def _official_report_int(self, report_payload, key, fallback_value):
        value = report_payload.get(key) if isinstance(report_payload, dict) else None
        if value in (None, ""):
            return fallback_value
        return int(Decimal(str(value)))

    def _residual_original_amount(self, official_sales_amount, by_category, rate):
        categorized_sales = sum((values["sales"] for values in by_category.values()), Decimal("0"))
        residual_sales = official_sales_amount - categorized_sales
        if not residual_sales:
            return Decimal("0")
        return (residual_sales / rate).quantize(MONEY_QUANT)

    def _skipped_products_payload(self, skipped_products):
        return [
            {"name": name, "qty": values["qty"], "original": str(values["original"])}
            for name, values in sorted(skipped_products.items())
        ]

    def _delete_existing_api_category_sales(self, options, sale_date):
        unit = BusinessUnit.objects.filter(slug=options["business_unit"]).first()
        country = Country.objects.filter(code=options["country"].upper()).first()
        channel = Channel.objects.filter(business_unit=unit, slug=options["channel_slug"]).first() if unit else None
        if not unit or not country or not channel:
            return
        DailyProductCategorySale.objects.filter(
            business_unit=unit,
            country=country,
            channel=channel,
            sale_date=sale_date,
            source_file="woocommerce-api",
        ).delete()
