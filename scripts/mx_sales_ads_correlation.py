import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import django


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings  # noqa: E402

from reports.integrations.clients import WooCommerceClient  # noqa: E402
from reports.services.sales_dashboard import uva_category_slug_from_product_name  # noqa: E402


DATE_FROM = date(2026, 6, 1)
DATE_TO = date(2026, 7, 6)
GOOGLE_JSON = Path("data") / "deep_google_mx_2026-07-07.json"
OUT = Path("data") / "mx_sales_ads_correlation_2026-07-07.json"
MICRO = Decimal("1000000")
STATUSES = ["completed", "on-hold", "processing"]


def daterange(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def dec(value):
    return Decimal(str(value or "0"))


def micros(value):
    return dec(value) / MICRO


def load_google_daily():
    payload = json.loads(GOOGLE_JSON.read_text(encoding="utf-8"))
    rows = payload["queries"]["campaign_daily"]["rows"]
    by_day = defaultdict(lambda: {"spend": Decimal("0"), "conversions": Decimal("0"), "clicks": 0, "impressions": 0})
    by_campaign = defaultdict(lambda: {"spend": Decimal("0"), "conversions": Decimal("0"), "clicks": 0, "impressions": 0})
    for row in rows:
        day = row["segments"]["date"]
        campaign = row["campaign"]["name"]
        metrics = row["metrics"]
        for bucket in (by_day[day], by_campaign[campaign]):
            bucket["spend"] += micros(metrics.get("costMicros"))
            bucket["conversions"] += dec(metrics.get("conversions"))
            bucket["clicks"] += int(dec(metrics.get("clicks")))
            bucket["impressions"] += int(dec(metrics.get("impressions")))
    return by_day, by_campaign


def summarize_woocommerce():
    base_url = getattr(settings, "WOOCOMMERCE_MX_BASE_URL", "")
    consumer_key = getattr(settings, "WOOCOMMERCE_MX_CONSUMER_KEY", "")
    consumer_secret = getattr(settings, "WOOCOMMERCE_MX_CONSUMER_SECRET", "")
    if not all([base_url, consumer_key, consumer_secret]):
        raise RuntimeError("Faltan credenciales WooCommerce MX.")

    client = WooCommerceClient(base_url, consumer_key, consumer_secret)
    tz = ZoneInfo(getattr(settings, "TIME_ZONE", "America/Bogota"))
    by_day = {}
    by_category = defaultdict(lambda: {"sales": Decimal("0"), "orders": 0, "units": 0, "products": defaultdict(int)})
    orders_out = []

    for target_date in daterange(DATE_FROM, DATE_TO):
        day_start = datetime.combine(target_date, time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        day_key = target_date.isoformat()
        day_bucket = {"sales": Decimal("0"), "orders": 0, "units": 0, "categories": defaultdict(lambda: {"sales": Decimal("0"), "units": 0})}
        for order in client.iter_orders_for_day(target_date, statuses=STATUSES, after=day_start.isoformat(), before=day_end.isoformat()):
            order_sales = Decimal("0")
            order_units = 0
            order_categories = set()
            for item in order.get("line_items", []):
                product_name = str(item.get("name") or "").strip()
                qty = int(item.get("quantity") or 0)
                line_total = dec(item.get("total"))
                if not product_name:
                    continue
                slug = uva_category_slug_from_product_name(product_name, {})
                if not slug:
                    slug = "otros-uva"
                order_sales += line_total
                order_units += qty
                order_categories.add(slug)
                day_bucket["categories"][slug]["sales"] += line_total
                day_bucket["categories"][slug]["units"] += qty
                by_category[slug]["sales"] += line_total
                by_category[slug]["units"] += qty
                by_category[slug]["products"][product_name] += qty
            if order_sales or order_units:
                day_bucket["sales"] += order_sales
                day_bucket["orders"] += 1
                day_bucket["units"] += order_units
                for slug in order_categories:
                    by_category[slug]["orders"] += 1
                orders_out.append(
                    {
                        "date": day_key,
                        "id": order.get("id"),
                        "status": order.get("status"),
                        "sales": str(order_sales),
                        "units": order_units,
                        "categories": sorted(order_categories),
                    }
                )
        by_day[day_key] = day_bucket
    return by_day, by_category, orders_out


def money(value):
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def main():
    google_day, google_campaign = load_google_daily()
    wc_day, wc_category, orders = summarize_woocommerce()
    daily = []
    for target_date in daterange(DATE_FROM, DATE_TO):
        key = target_date.isoformat()
        ads = google_day[key]
        sales = wc_day[key]
        spend = ads["spend"]
        conversations = ads["conversions"]
        revenue = sales["sales"]
        orders_count = sales["orders"]
        daily.append(
            {
                "date": key,
                "google_spend_mxn": money(spend),
                "whatsapp_conversions": str(conversations.quantize(Decimal("0.01"))),
                "woocommerce_sales_mxn": money(revenue),
                "woocommerce_orders": orders_count,
                "units": sales["units"],
                "conversation_to_order_rate": str(((Decimal(orders_count) / conversations) if conversations else Decimal("0")).quantize(Decimal("0.0001"))),
                "ads_to_sales_ratio": str(((spend / revenue) if revenue else Decimal("0")).quantize(Decimal("0.0001"))),
                "blended_roas": str(((revenue / spend) if spend else Decimal("0")).quantize(Decimal("0.01"))),
                "categories": {
                    slug: {"sales": money(values["sales"]), "units": values["units"]}
                    for slug, values in sales["categories"].items()
                },
            }
        )

    payload = {
        "date_from": DATE_FROM.isoformat(),
        "date_to": DATE_TO.isoformat(),
        "daily": daily,
        "summary": {
            "google_spend_mxn": money(sum((item["spend"] for item in google_day.values()), Decimal("0"))),
            "whatsapp_conversions": str(sum((item["conversions"] for item in google_day.values()), Decimal("0")).quantize(Decimal("0.01"))),
            "woocommerce_sales_mxn": money(sum((item["sales"] for item in wc_day.values()), Decimal("0"))),
            "woocommerce_orders": sum((item["orders"] for item in wc_day.values()), 0),
            "units": sum((item["units"] for item in wc_day.values()), 0),
        },
        "google_by_campaign": {
            campaign: {
                "spend_mxn": money(values["spend"]),
                "whatsapp_conversions": str(values["conversions"].quantize(Decimal("0.01"))),
                "clicks": values["clicks"],
                "impressions": values["impressions"],
            }
            for campaign, values in google_campaign.items()
        },
        "woocommerce_by_category": {
            slug: {
                "sales_mxn": money(values["sales"]),
                "orders": values["orders"],
                "units": values["units"],
                "top_products": sorted(values["products"].items(), key=lambda item: item[1], reverse=True)[:12],
            }
            for slug, values in wc_category.items()
        },
        "orders": orders,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()
