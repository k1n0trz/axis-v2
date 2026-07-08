import json
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import django
import requests


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.conf import settings  # noqa: E402

from reports.integrations.clients import GoogleAdsClient  # noqa: E402


DATE_FROM = date(2026, 6, 1)
DATE_TO = date(2026, 7, 6)
TODAY = date(2026, 7, 7)
OUT = Path("data") / f"deep_ads_audit_{TODAY.isoformat()}.json"

META_ACCOUNT_ID = "3473366029576347"
META_CAMPAIGN_HINTS = [
    "02/07/26 | Ventas | Hidratante",
    "26/06/26 | Ventas | Ugc",
    "10/11/25 | Ventas | UGC",
]

GOOGLE_ACCOUNTS = {
    "bali": {
        "customer_id": "4042093126",
        "campaign_hints": ["19/06/26 | Ventas | Search | Lovense", "11/09/25 | Shopping | P-Max | COL"],
    },
    "laboratorio_helti": {"customer_id": "3866881158", "campaign_hints": []},
    "uva_ecuador": {"customer_id": "6385600284", "campaign_hints": []},
    "copa_uva_mx": {"customer_id": "6145165793", "campaign_hints": []},
}

MICRO = Decimal("1000000")


def dec(value):
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def money_from_micros(value):
    return dec(value) / MICRO


def action_total(actions, needles):
    total = Decimal("0")
    for action in actions or []:
        name = str(action.get("action_type") or "").lower()
        if any(needle in name for needle in needles):
            total += dec(action.get("value"))
    return total


def metric_summary(rows):
    total = {
        "spend": Decimal("0"),
        "impressions": Decimal("0"),
        "reach": Decimal("0"),
        "clicks": Decimal("0"),
        "inline_link_clicks": Decimal("0"),
        "purchases": Decimal("0"),
        "purchase_value": Decimal("0"),
    }
    for row in rows or []:
        total["spend"] += dec(row.get("spend"))
        total["impressions"] += dec(row.get("impressions"))
        total["reach"] += dec(row.get("reach"))
        total["clicks"] += dec(row.get("clicks"))
        total["inline_link_clicks"] += dec(row.get("inline_link_clicks"))
        total["purchases"] += action_total(row.get("actions"), ["purchase"])
        total["purchase_value"] += action_total(row.get("action_values"), ["purchase"])

    spend = total["spend"]
    clicks = total["clicks"]
    link_clicks = total["inline_link_clicks"]
    impressions = total["impressions"]
    purchases = total["purchases"]
    value = total["purchase_value"]
    total["ctr"] = (clicks / impressions * 100) if impressions else None
    total["link_ctr"] = (link_clicks / impressions * 100) if impressions else None
    total["cpc"] = (spend / clicks) if clicks else None
    total["cpm"] = (spend / impressions * 1000) if impressions else None
    total["cpa_purchase"] = (spend / purchases) if purchases else None
    total["roas_purchase_value"] = (value / spend) if spend else None
    return {key: str(value.quantize(Decimal("0.01"))) if isinstance(value, Decimal) else value for key, value in total.items()}


class MetaReader:
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/{getattr(settings, 'META_API_VERSION', 'v20.0')}"
        self.token = getattr(settings, "META_ACCESS_TOKEN", "")
        self.session = requests.Session()
        self.errors = []

    def get_all(self, path, params, label):
        params = dict(params or {})
        params["access_token"] = self.token
        payload = []
        url = f"{self.base_url}{path}" if path.startswith("/") else path
        while url:
            response = self.session.get(url, params=params, timeout=60)
            if not response.ok:
                self.errors.append({"label": label, "status": response.status_code, "body": response.text[:800]})
                return payload
            body = response.json()
            payload.extend(body.get("data", []))
            url = body.get("paging", {}).get("next")
            params = None
        return payload

    def campaign_catalog(self, account_id):
        fields = ",".join(
            [
                "id",
                "name",
                "status",
                "effective_status",
                "objective",
                "buying_type",
                "bid_strategy",
                "daily_budget",
                "lifetime_budget",
                "budget_remaining",
                "created_time",
                "start_time",
                "stop_time",
                "updated_time",
                "special_ad_categories",
                "configured_status",
            ]
        )
        return self.get_all(f"/act_{account_id}/campaigns", {"fields": fields, "limit": 500}, "meta_campaign_catalog")

    def insights(self, account_id, level, since, until, campaign_ids=None, breakdowns=None):
        base_fields = [
            "campaign_id",
            "campaign_name",
            "adset_id",
            "adset_name",
            "ad_id",
            "ad_name",
            "spend",
            "impressions",
            "reach",
            "frequency",
            "clicks",
            "inline_link_clicks",
            "ctr",
            "cpc",
            "cpm",
            "actions",
            "action_values",
            "cost_per_action_type",
            "purchase_roas",
            "website_purchase_roas",
            "quality_ranking",
            "engagement_rate_ranking",
            "conversion_rate_ranking",
        ]
        params = {
            "level": level,
            "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
            "fields": ",".join(base_fields),
            "limit": 500,
        }
        if campaign_ids:
            params["filtering"] = json.dumps([{"field": "campaign.id", "operator": "IN", "value": campaign_ids}])
        if breakdowns:
            params["breakdowns"] = ",".join(breakdowns)
        rows = self.get_all(f"/act_{account_id}/insights", params, f"meta_insights_{level}")
        if not rows and base_fields[-3:]:
            params["fields"] = ",".join(base_fields[:-3])
            rows = self.get_all(f"/act_{account_id}/insights", params, f"meta_insights_{level}_fallback")
        return rows

    def adsets(self, account_id, campaign_ids):
        fields = ",".join(
            [
                "id",
                "name",
                "campaign_id",
                "status",
                "effective_status",
                "optimization_goal",
                "billing_event",
                "bid_strategy",
                "bid_amount",
                "daily_budget",
                "lifetime_budget",
                "budget_remaining",
                "start_time",
                "end_time",
                "attribution_spec",
                "promoted_object",
                "targeting",
            ]
        )
        return self.get_all(
            f"/act_{account_id}/adsets",
            {
                "fields": fields,
                "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": campaign_ids}]),
                "limit": 500,
            },
            "meta_adsets",
        )

    def ads(self, account_id, campaign_ids):
        fields = ",".join(
            [
                "id",
                "name",
                "campaign{id,name}",
                "adset{id,name}",
                "status",
                "effective_status",
                "created_time",
                "updated_time",
                "creative{id,name,title,body,thumbnail_url,image_url,object_url,link_url,call_to_action_type,object_story_spec,asset_feed_spec}",
            ]
        )
        return self.get_all(
            f"/act_{account_id}/ads",
            {
                "fields": fields,
                "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": campaign_ids}]),
                "limit": 500,
            },
            "meta_ads",
        )


class GoogleReader:
    def __init__(self):
        self.client = GoogleAdsClient(
            developer_token=getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            client_id=getattr(settings, "GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", ""),
            login_customer_id=getattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
        )

    def search(self, customer_id, query, label):
        try:
            batches = self.client.search(customer_id, query)
            rows = []
            for batch in batches:
                rows.extend(batch.get("results", []))
            return {"label": label, "rows": rows, "error": ""}
        except Exception as exc:
            return {"label": label, "rows": [], "error": str(exc)[:1200]}

    def audit_account(self, customer_id):
        start = DATE_FROM.isoformat()
        end = DATE_TO.isoformat()
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
                  metrics.cost_micros,
                  metrics.impressions,
                  metrics.clicks,
                  metrics.ctr,
                  metrics.average_cpc,
                  metrics.conversions,
                  metrics.conversions_value,
                  metrics.all_conversions,
                  metrics.search_impression_share,
                  metrics.search_budget_lost_impression_share,
                  metrics.search_rank_lost_impression_share
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
                  ad_group_criterion.criterion_id,
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
                LIMIT 200
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
            "ads": f"""
                SELECT
                  campaign.id,
                  campaign.name,
                  ad_group.name,
                  ad_group_ad.ad.id,
                  ad_group_ad.status,
                  ad_group_ad.ad.type,
                  ad_group_ad.ad.responsive_search_ad.headlines,
                  ad_group_ad.ad.responsive_search_ad.descriptions,
                  metrics.cost_micros,
                  metrics.impressions,
                  metrics.clicks,
                  metrics.conversions,
                  metrics.conversions_value
                FROM ad_group_ad
                WHERE segments.date BETWEEN '{start}' AND '{end}'
                ORDER BY metrics.cost_micros DESC
                LIMIT 150
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
                LIMIT 150
            """,
            "shopping": f"""
                SELECT
                  campaign.id,
                  campaign.name,
                  segments.product_item_id,
                  segments.product_title,
                  segments.product_brand,
                  segments.product_channel,
                  metrics.cost_micros,
                  metrics.impressions,
                  metrics.clicks,
                  metrics.conversions,
                  metrics.conversions_value
                FROM shopping_performance_view
                WHERE segments.date BETWEEN '{start}' AND '{end}'
                ORDER BY metrics.cost_micros DESC
                LIMIT 250
            """,
        }
        results = {name: self.search(customer_id, query, name) for name, query in queries.items()}
        return results


def google_summaries(query_results):
    rows = query_results.get("campaign_daily", {}).get("rows") or []
    by_campaign = defaultdict(
        lambda: {
            "cost": Decimal("0"),
            "impressions": Decimal("0"),
            "clicks": Decimal("0"),
            "conversions": Decimal("0"),
            "value": Decimal("0"),
            "status": "",
            "channel": "",
            "subchannel": "",
            "bidding": "",
            "budget": Decimal("0"),
        }
    )
    for row in rows:
        campaign = row.get("campaign", {})
        metrics = row.get("metrics", {})
        budget = row.get("campaignBudget", {})
        key = f"{campaign.get('id')} | {campaign.get('name')}"
        bucket = by_campaign[key]
        bucket["cost"] += money_from_micros(metrics.get("costMicros"))
        bucket["impressions"] += dec(metrics.get("impressions"))
        bucket["clicks"] += dec(metrics.get("clicks"))
        bucket["conversions"] += dec(metrics.get("conversions"))
        bucket["value"] += dec(metrics.get("conversionsValue"))
        bucket["status"] = campaign.get("status", "")
        bucket["channel"] = campaign.get("advertisingChannelType", "")
        bucket["subchannel"] = campaign.get("advertisingChannelSubType", "")
        bucket["bidding"] = campaign.get("biddingStrategyType", "")
        bucket["budget"] = money_from_micros(budget.get("amountMicros"))

    payload = []
    for name, data in sorted(by_campaign.items(), key=lambda item: item[1]["cost"], reverse=True):
        cost = data["cost"]
        conv = data["conversions"]
        clicks = data["clicks"]
        impressions = data["impressions"]
        payload.append(
            {
                "campaign": name,
                "status": data["status"],
                "channel": data["channel"],
                "subchannel": data["subchannel"],
                "bidding": data["bidding"],
                "daily_budget": str(data["budget"].quantize(Decimal("0.01"))),
                "cost": str(cost.quantize(Decimal("0.01"))),
                "impressions": str(impressions),
                "clicks": str(clicks),
                "ctr": str(((clicks / impressions * 100) if impressions else Decimal("0")).quantize(Decimal("0.01"))),
                "conversions": str(conv.quantize(Decimal("0.01"))),
                "conv_value": str(data["value"].quantize(Decimal("0.01"))),
                "cpa": str(((cost / conv) if conv else Decimal("0")).quantize(Decimal("0.01"))),
                "roas": str(((data["value"] / cost) if cost else Decimal("0")).quantize(Decimal("0.02"))),
            }
        )
    return payload


def main():
    report = {
        "generated_at": TODAY.isoformat(),
        "date_from": DATE_FROM.isoformat(),
        "date_to": DATE_TO.isoformat(),
        "meta": {},
        "google": {},
    }

    meta = MetaReader()
    campaigns = meta.campaign_catalog(META_ACCOUNT_ID)
    selected = [
        item
        for item in campaigns
        if any(hint.lower() in str(item.get("name", "")).lower() for hint in META_CAMPAIGN_HINTS)
    ]
    selected_ids = [item["id"] for item in selected]
    meta_campaign_rows = meta.insights(META_ACCOUNT_ID, "campaign", DATE_FROM, DATE_TO, campaign_ids=selected_ids or None)
    if not selected_ids:
        selected_ids = [
            row.get("campaign_id")
            for row in meta_campaign_rows
            if any(hint.lower() in str(row.get("campaign_name", "")).lower() for hint in META_CAMPAIGN_HINTS)
        ]
        selected_ids = list(dict.fromkeys([value for value in selected_ids if value]))
    report["meta"] = {
        "account_id": META_ACCOUNT_ID,
        "campaign_hints": META_CAMPAIGN_HINTS,
        "selected_campaigns": selected,
        "selected_campaign_ids": selected_ids,
        "campaign_insights": meta.insights(META_ACCOUNT_ID, "campaign", DATE_FROM, DATE_TO, campaign_ids=selected_ids),
        "adset_insights": meta.insights(META_ACCOUNT_ID, "adset", DATE_FROM, DATE_TO, campaign_ids=selected_ids),
        "ad_insights": meta.insights(META_ACCOUNT_ID, "ad", DATE_FROM, DATE_TO, campaign_ids=selected_ids),
        "placement_breakdown": meta.insights(
            META_ACCOUNT_ID,
            "ad",
            DATE_FROM,
            DATE_TO,
            campaign_ids=selected_ids,
            breakdowns=["publisher_platform", "platform_position", "device_platform"],
        ),
        "adsets": meta.adsets(META_ACCOUNT_ID, selected_ids) if selected_ids else [],
        "ads": meta.ads(META_ACCOUNT_ID, selected_ids) if selected_ids else [],
        "errors": meta.errors,
    }
    report["meta"]["summary"] = {
        "campaign": metric_summary(report["meta"]["campaign_insights"]),
        "adset": metric_summary(report["meta"]["adset_insights"]),
        "ad": metric_summary(report["meta"]["ad_insights"]),
    }

    google = GoogleReader()
    for slug, config in GOOGLE_ACCOUNTS.items():
        customer_id = config["customer_id"]
        results = google.audit_account(customer_id)
        report["google"][slug] = {
            "customer_id": customer_id,
            "campaign_hints": config["campaign_hints"],
            "queries": results,
            "campaign_summary": google_summaries(results),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()

