import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from reports.models import ComfamaAdMetric, DailyAdSpend, DailyProductCategoryMetric


ZERO = Decimal("0")


def money(value):
    amount = value if value is not None else ZERO
    return str(amount.quantize(Decimal("0.01")))


def maybe_decimal(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))


class Command(BaseCommand):
    help = "Audita inversion de pauta por plataforma/categoria para un rango."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", required=True)
        parser.add_argument("--date-to", required=True)
        parser.add_argument("--country", default="CO")
        parser.add_argument("--business-unit", default="uva")
        parser.add_argument("--expected-meta", default="")
        parser.add_argument("--expected-google", default="")

    def handle(self, *args, **options):
        start_date = date.fromisoformat(options["date_from"])
        end_date = date.fromisoformat(options["date_to"])
        country_code = options["country"].upper()
        business_unit = options["business_unit"]
        expected_meta = maybe_decimal(options["expected_meta"])
        expected_google = maybe_decimal(options["expected_google"])

        spend_rows = list(
            DailyAdSpend.objects.filter(
                country__code=country_code,
                spend_date__range=(start_date, end_date),
            )
            .values("business_unit__slug", "ad_platform__slug")
            .annotate(total=Sum("spend_amount"))
            .order_by("business_unit__slug", "ad_platform__slug")
        )
        spend_by_key = {
            (row["business_unit__slug"], row["ad_platform__slug"]): row["total"] or ZERO
            for row in spend_rows
        }

        category_rows = list(
            DailyProductCategoryMetric.objects.filter(
                business_unit__slug=business_unit,
                country__code=country_code,
                metric_date__range=(start_date, end_date),
            )
            .values("category__slug", "category__name")
            .annotate(
                meta=Sum("spend_meta"),
                google=Sum("spend_google"),
                total=Sum("total_spend"),
            )
            .order_by("category__slug")
        )
        category_payload = [
            {
                "category": row["category__slug"],
                "name": row["category__name"],
                "meta": money(row["meta"]),
                "google": money(row["google"]),
                "total": money(row["total"]),
            }
            for row in category_rows
        ]
        category_meta_total = sum((row["meta"] or ZERO for row in category_rows), ZERO)
        category_google_total = sum((row["google"] or ZERO for row in category_rows), ZERO)

        comfama_spend = spend_by_key.get(("comfama-uva", "meta-ads"), ZERO)
        comfama_category_rows = list(
            ComfamaAdMetric.objects.filter(metric_date__range=(start_date, end_date))
            .values("category__slug", "category__name")
            .annotate(meta=Sum("spend_amount"))
            .order_by("category__slug")
        )
        comfama_category_total = sum((row["meta"] or ZERO for row in comfama_category_rows), ZERO)

        uva_meta_spend = spend_by_key.get((business_unit, "meta-ads"), ZERO)
        uva_google_spend = spend_by_key.get((business_unit, "google-ads"), ZERO)
        meta_total_with_comfama = uva_meta_spend + comfama_spend

        payload = {
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "country": country_code,
            "daily_spend_by_unit_platform": [
                {
                    "business_unit": row["business_unit__slug"],
                    "platform": row["ad_platform__slug"],
                    "total": money(row["total"]),
                }
                for row in spend_rows
            ],
            "uva_category_metrics": category_payload,
            "comfama_category_metrics": [
                {
                    "category": row["category__slug"],
                    "name": row["category__name"],
                    "meta": money(row["meta"]),
                }
                for row in comfama_category_rows
            ],
            "reconciliation": {
                "meta_uva_daily": money(uva_meta_spend),
                "meta_uva_categories": money(category_meta_total),
                "meta_uva_unallocated": money(uva_meta_spend - category_meta_total),
                "meta_comfama_daily": money(comfama_spend),
                "meta_comfama_categories": money(comfama_category_total),
                "meta_comfama_unallocated": money(comfama_spend - comfama_category_total),
                "meta_total_with_comfama": money(meta_total_with_comfama),
                "meta_expected": money(expected_meta) if expected_meta is not None else "",
                "meta_expected_delta": money(meta_total_with_comfama - expected_meta) if expected_meta is not None else "",
                "google_uva_daily": money(uva_google_spend),
                "google_uva_categories": money(category_google_total),
                "google_uva_unallocated": money(uva_google_spend - category_google_total),
                "google_expected": money(expected_google) if expected_google is not None else "",
                "google_expected_delta": money(uva_google_spend - expected_google) if expected_google is not None else "",
            },
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))
