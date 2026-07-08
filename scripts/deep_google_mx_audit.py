import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import django


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings  # noqa: E402

from reports.integrations.clients import GoogleAdsClient  # noqa: E402


CUSTOMER_ID = "6143715017"
DATE_FROM = date(2026, 6, 1)
DATE_TO = date(2026, 7, 6)
OUT = Path("data") / "deep_google_mx_2026-07-07.json"
MICRO = Decimal("1000000")


def query(client, name, gaql):
    try:
        batches = client.search(CUSTOMER_ID, gaql)
        rows = []
        for batch in batches:
            rows.extend(batch.get("results", []))
        return {"name": name, "rows": rows, "error": ""}
    except Exception as exc:
        return {"name": name, "rows": [], "error": str(exc)[:1200]}


def main():
    start = DATE_FROM.isoformat()
    end = DATE_TO.isoformat()
    client = GoogleAdsClient(
        developer_token=getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", ""),
        client_id=getattr(settings, "GOOGLE_ADS_CLIENT_ID", ""),
        client_secret=getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", ""),
        refresh_token=getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", ""),
        login_customer_id=getattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
    )
    queries = {
        "campaign_daily": f"""
            SELECT
              segments.date,
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              campaign.advertising_channel_sub_type,
              campaign.bidding_strategy_type,
              campaign_budget.amount_micros,
              customer.currency_code,
              metrics.cost_micros,
              metrics.impressions,
              metrics.clicks,
              metrics.ctr,
              metrics.average_cpc,
              metrics.conversions,
              metrics.conversions_value,
              metrics.all_conversions
            FROM campaign
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            ORDER BY metrics.cost_micros DESC
        """,
        "ad_group": f"""
            SELECT
              campaign.id,
              campaign.name,
              ad_group.id,
              ad_group.name,
              ad_group.status,
              ad_group.type,
              metrics.cost_micros,
              metrics.impressions,
              metrics.clicks,
              metrics.conversions,
              metrics.conversions_value
            FROM ad_group
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            ORDER BY metrics.cost_micros DESC
            LIMIT 200
        """,
        "keywords": f"""
            SELECT
              campaign.id,
              campaign.name,
              ad_group.name,
              ad_group_criterion.status,
              ad_group_criterion.keyword.text,
              ad_group_criterion.keyword.match_type,
              ad_group_criterion.quality_info.quality_score,
              metrics.cost_micros,
              metrics.impressions,
              metrics.clicks,
              metrics.conversions,
              metrics.conversions_value
            FROM keyword_view
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            ORDER BY metrics.cost_micros DESC
            LIMIT 250
        """,
        "search_terms": f"""
            SELECT
              campaign.id,
              campaign.name,
              ad_group.name,
              search_term_view.search_term,
              search_term_view.status,
              metrics.cost_micros,
              metrics.impressions,
              metrics.clicks,
              metrics.conversions,
              metrics.conversions_value
            FROM search_term_view
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            ORDER BY metrics.cost_micros DESC
            LIMIT 250
        """,
        "asset_groups": f"""
            SELECT
              campaign.id,
              campaign.name,
              asset_group.id,
              asset_group.name,
              asset_group.status,
              metrics.cost_micros,
              metrics.impressions,
              metrics.clicks,
              metrics.conversions,
              metrics.conversions_value
            FROM asset_group
            WHERE segments.date BETWEEN '{start}' AND '{end}'
            ORDER BY metrics.cost_micros DESC
            LIMIT 100
        """,
    }
    payload = {
        "customer_id": CUSTOMER_ID,
        "date_from": start,
        "date_to": end,
        "queries": {name: query(client, name, gaql) for name, gaql in queries.items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()
