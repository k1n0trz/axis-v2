import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from reports.models import DailyChannelSale, DailyProductCategorySale
from reports.services.sales_dashboard import build_sales_snapshot, build_uva_category_snapshot


def decimal_value(value):
    return str(value if value is not None else Decimal("0"))


class Command(BaseCommand):
    help = "Audita ventas web Uva por categoria para un rango sin exponer credenciales ni payloads de ordenes."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", required=True)
        parser.add_argument("--date-to", required=True)
        parser.add_argument("--country", default="CO")
        parser.add_argument("--business-unit", default="uva")
        parser.add_argument("--channel-slug", default="ecommerce-uva")

    def handle(self, *args, **options):
        date_from = date.fromisoformat(options["date_from"])
        date_to = date.fromisoformat(options["date_to"])
        filters = {
            "date_start": date_from.isoformat(),
            "date_end": date_to.isoformat(),
            "country": options["country"],
            "business_unit": options["business_unit"],
        }

        category_rows = (
            DailyProductCategorySale.objects.filter(
                business_unit__slug=options["business_unit"],
                country__code=options["country"],
                channel__slug=options["channel_slug"],
                sale_date__gte=date_from,
                sale_date__lte=date_to,
            )
            .values("category__slug", "category__name", "source_file")
            .annotate(sales=Sum("sales_amount"), quantity=Sum("quantity"))
            .order_by("-sales", "category__slug", "source_file")
        )
        channel_rows = (
            DailyChannelSale.objects.filter(
                business_unit__slug=options["business_unit"],
                country__code=options["country"],
                channel__slug=options["channel_slug"],
                sale_date__gte=date_from,
                sale_date__lte=date_to,
            )
            .values("source_file")
            .annotate(sales=Sum("sales_amount"), orders=Sum("order_count"), units=Sum("units"))
            .order_by("source_file")
        )

        category_snapshot = build_uva_category_snapshot(filters)
        sales_snapshot = build_sales_snapshot(filters, include_comparison=False)

        payload = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "country": options["country"],
            "channel": options["channel_slug"],
            "channel_totals": [
                {
                    "source_file": row["source_file"],
                    "sales": decimal_value(row["sales"]),
                    "orders": row["orders"] or 0,
                    "units": row["units"] or 0,
                }
                for row in channel_rows
            ],
            "category_totals": [
                {
                    "category_slug": row["category__slug"],
                    "category_name": row["category__name"],
                    "source_file": row["source_file"],
                    "sales": decimal_value(row["sales"]),
                    "quantity": row["quantity"] or 0,
                }
                for row in category_rows
            ],
            "dashboard_kpis": sales_snapshot["kpis"],
            "category_cards": [
                {
                    "name": card["name"],
                    "sales_total": card["sales_total"],
                    "web_sales_total": card.get("web_sales_total", 0),
                    "web_units": card.get("web_units", 0),
                    "whatsapp_sales_total": card.get("whatsapp_sales_total", 0),
                    "whatsapp_units": card.get("whatsapp_units", 0),
                }
                for card in category_snapshot.get("cards", [])
            ],
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))
