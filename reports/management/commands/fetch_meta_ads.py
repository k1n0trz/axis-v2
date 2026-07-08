import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from reports.integrations.axis_sync import AxisSyncService
from reports.integrations.clients import ExchangeRateClient, MetaAdsClient, load_json_mapping, match_rule
from reports.integrations.schema import AdSpendRecord, CategoryMetricRecord, ComfamaAdMetricRecord, FollowerMetricRecord
from reports.services.sales_dashboard import uva_exchange_rate_for_country


def action_value(actions, action_type):
    for action in actions or []:
        if action.get("action_type") == action_type:
            return Decimal(str(action.get("value") or "0"))
    return Decimal("0")


def action_value_contains(actions, keywords):
    total = Decimal("0")
    for action in actions or []:
        action_name = str(action.get("action_type") or "").strip().lower()
        if any(keyword in action_name for keyword in keywords):
            total += Decimal(str(action.get("value") or "0"))
    return total


def cost_value_contains(cost_items, keywords):
    for item in cost_items or []:
        action_name = str(item.get("action_type") or "").strip().lower()
        if any(keyword in action_name for keyword in keywords):
            return Decimal(str(item.get("value") or "0"))
    return Decimal("0")


FOLLOWER_MATCH_KEYWORDS = [
    "visitas ig",
    "seguidores",
    "perfil",
    "profile",
    "instagram",
]

PROFILE_VISIT_ACTION_KEYWORDS = [
    "profile_visit",
    "instagram_profile_visit",
    "visit_instagram_profile",
]

FOLLOW_ACTION_KEYWORDS = [
    "follow",
    "follower",
]

COMFAMA_MATCH_KEYWORDS = [
    "comfama",
]

CONVERSATION_ACTION_KEYWORDS = [
    "messaging_conversation",
    "onsite_conversion.messaging_conversation_started",
    "onsite_conversion.total_messaging_connection",
    "link_click_to_messaging_conversation",
    "lead",
]


class Command(BaseCommand):
    help = "Consulta Meta Ads y devuelve inversion y CPA por campana/categoria."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True)
        parser.add_argument("--country", required=True)
        parser.add_argument("--account-id", default="")
        parser.add_argument("--business-unit", default="uva")
        parser.add_argument("--rules", default="")
        parser.add_argument("--currency", default="COP")
        parser.add_argument("--target-currency", default="COP")
        parser.add_argument("--meta-token", default="")
        parser.add_argument("--api-version", default="")
        parser.add_argument("--fx-url", default="")
        parser.add_argument("--fx-key", default="")
        parser.add_argument("--level", default="adset")
        parser.add_argument("--debug-actions", action="store_true")
        parser.add_argument("--sync-axis", action="store_true")

    def handle(self, *args, **options):
        country_code = options["country"].upper()
        account_id = options["account_id"] or getattr(settings, f"META_{country_code}_ACCOUNT_ID", "")
        meta_token = options["meta_token"] or getattr(settings, "META_ACCESS_TOKEN", "")
        api_version = options["api_version"] or getattr(settings, "META_API_VERSION", "v20.0")
        fx_url = options["fx_url"] or getattr(settings, "EXCHANGE_RATE_API_URL", "https://api.exchangerate.host")
        fx_key = options["fx_key"] or getattr(settings, "EXCHANGE_RATE_API_KEY", "")
        if not account_id or not meta_token:
            raise CommandError("Faltan credenciales de Meta Ads.")

        target_date = date.fromisoformat(options["date"])
        mapping_payload = load_json_mapping(options["rules"]) if options["rules"] else {}
        country_rules = mapping_payload.get("country_rules", {}).get(country_code, {})
        rules = list(mapping_payload.get("rules", [])) + list(country_rules.get("rules", []))
        follower_rules = list(mapping_payload.get("follower_rules", [])) + list(country_rules.get("follower_rules", []))
        fx = ExchangeRateClient(fx_url, api_key=fx_key)
        client = MetaAdsClient(meta_token, api_version=api_version)
        insights = client.get_campaign_insights(account_id, target_date, level=options["level"])
        spend_total = Decimal("0")
        comfama_spend_total = Decimal("0")
        spend_by_category = defaultdict(lambda: {"meta": Decimal("0"), "results": Decimal("0"), "name": "", "campaign": ""})
        comfama_by_category = defaultdict(lambda: {"spend": Decimal("0"), "conversations": Decimal("0"), "name": "", "campaign": ""})
        follower_metrics = []
        follower_spend = Decimal("0")
        follower_profile_visits = Decimal("0")
        follower_new_followers = Decimal("0")
        follower_notes = []
        follower_debug_rows = []
        unmatched_campaigns = []

        for row in insights:
            campaign_name = row.get("campaign_name", "")
            adset_name = row.get("adset_name", "")
            match_source = adset_name or campaign_name
            spend = Decimal(str(row.get("spend") or "0"))
            account_currency = row.get("account_currency") or options["currency"]
            if account_currency == options["target_currency"]:
                spend_cop = spend
            else:
                fixed_rate = uva_exchange_rate_for_country(country_code, account_currency)
                spend_cop = spend * fixed_rate if fixed_rate != Decimal("1") else fx.convert(account_currency, options["target_currency"], spend, target_date=target_date)
            follower_metric_slug = match_rule(match_source, follower_rules) or match_rule(campaign_name, follower_rules)
            lowered_source = str(match_source or "").strip().lower()
            lowered_campaign = str(campaign_name or "").strip().lower()
            is_comfama_campaign = country_code == "CO" and (
                any(keyword in lowered_source for keyword in COMFAMA_MATCH_KEYWORDS)
                or any(keyword in lowered_campaign for keyword in COMFAMA_MATCH_KEYWORDS)
            )
            if is_comfama_campaign:
                category_slug = match_rule(match_source, rules) or match_rule(campaign_name, rules)
                conversations = action_value_contains(row.get("actions"), CONVERSATION_ACTION_KEYWORDS)
                if not conversations:
                    derived_cpl = cost_value_contains(row.get("cost_per_action_type"), CONVERSATION_ACTION_KEYWORDS)
                    conversations = (spend_cop / derived_cpl) if derived_cpl else Decimal("0")
                comfama_spend_total += spend_cop
                if category_slug:
                    comfama_by_category[category_slug]["spend"] += spend_cop
                    comfama_by_category[category_slug]["conversations"] += conversations
                    comfama_by_category[category_slug]["name"] = adset_name or campaign_name
                    comfama_by_category[category_slug]["campaign"] = campaign_name
                else:
                    unmatched_campaigns.append(
                        {
                            "campaign_name": campaign_name,
                            "adset_name": adset_name,
                            "spend_amount": spend_cop,
                            "account_currency": account_currency,
                            "bucket": "comfama",
                        }
                    )
                continue
            spend_total += spend_cop
            is_follower_campaign = bool(
                follower_metric_slug
                or any(keyword in lowered_source for keyword in FOLLOWER_MATCH_KEYWORDS)
                or any(keyword in lowered_campaign for keyword in FOLLOWER_MATCH_KEYWORDS)
            )
            if is_follower_campaign:
                actions = row.get("actions") or []
                cost_items = row.get("cost_per_action_type") or []
                visits = action_value_contains(actions, PROFILE_VISIT_ACTION_KEYWORDS)
                followers = action_value_contains(actions, FOLLOW_ACTION_KEYWORDS)
                if not visits:
                    derived_cpr = cost_value_contains(cost_items, PROFILE_VISIT_ACTION_KEYWORDS)
                    visits = (spend_cop / derived_cpr) if derived_cpr else Decimal("0")
                follower_spend += spend_cop
                follower_profile_visits += visits
                follower_new_followers += followers
                follower_notes.append(f"{adset_name or campaign_name}")
                if options["debug_actions"]:
                    follower_debug_rows.append(
                        {
                            "campaign_name": campaign_name,
                            "adset_name": adset_name,
                            "spend_amount": spend_cop,
                            "actions": actions,
                            "cost_per_action_type": cost_items,
                        }
                    )
                continue
            category_slug = match_rule(match_source, rules) or match_rule(campaign_name, rules)
            if not category_slug:
                if spend_cop > 0:
                    unmatched_campaigns.append(
                        {
                            "campaign_name": campaign_name,
                            "adset_name": adset_name,
                            "spend_amount": spend_cop,
                            "account_currency": account_currency,
                            "bucket": "uva",
                        }
                    )
                continue
            purchases = action_value(row.get("actions"), "purchase") or action_value(row.get("actions"), "onsite_web_purchase")
            spend_by_category[category_slug]["meta"] += spend_cop
            spend_by_category[category_slug]["results"] += purchases
            spend_by_category[category_slug]["name"] = adset_name or campaign_name
            spend_by_category[category_slug]["campaign"] = campaign_name

        ad_spend = AdSpendRecord(
            business_unit_slug=options["business_unit"],
            country_code=country_code,
            ad_platform_slug="meta-ads",
            spend_date=target_date,
            spend_amount=spend_total,
            source_file="meta-ads-api",
            notes=f"Cuenta Meta {account_id}.",
        )
        category_metrics = []
        for slug, values in sorted(spend_by_category.items()):
            cpa = (values["meta"] / values["results"]) if values["results"] else None
            category_metrics.append(
                CategoryMetricRecord(
                    business_unit_slug=options["business_unit"],
                    country_code=country_code,
                    category_slug=slug,
                    category_name=slug.replace("-", " ").title(),
                    metric_date=target_date,
                    cpa_meta=cpa,
                    spend_meta=values["meta"],
                    source_file="meta-ads-api",
                    notes=f"Conjunto base: {values['name']} | Campana: {values['campaign']}",
                )
            )

        comfama_spend_record = None
        comfama_metrics = []
        if comfama_spend_total > 0:
            comfama_spend_record = AdSpendRecord(
                business_unit_slug="comfama-uva",
                country_code="CO",
                ad_platform_slug="meta-ads",
                spend_date=target_date,
                spend_amount=comfama_spend_total,
                source_file="meta-ads-api",
                notes=f"Cuenta Meta {account_id}. Importado desde campañas Comfama.",
            )
            for slug, values in sorted(comfama_by_category.items()):
                conversations = int(values["conversations"])
                cpl = (values["spend"] / values["conversations"]) if values["conversations"] else Decimal("0")
                comfama_metrics.append(
                    ComfamaAdMetricRecord(
                        metric_date=target_date,
                        category_slug=slug,
                        category_name=slug.replace("-", " ").title(),
                        cpl=cpl,
                        spend_amount=values["spend"],
                        conversations=conversations,
                        source_file="meta-ads-api",
                        notes=f"Conjunto base: {values['name']} | Campana: {values['campaign']}",
                    )
                )

        if follower_spend > 0 or follower_profile_visits > 0 or follower_new_followers > 0:
            visits_int = int(follower_profile_visits)
            followers_int = int(follower_new_followers)
            follower_metrics.append(
                FollowerMetricRecord(
                    country_code=country_code,
                    metric_date=target_date,
                    instagram_profile_visits=visits_int,
                    new_followers=followers_int,
                    spend_amount=follower_spend,
                    cpr=(follower_spend / follower_profile_visits) if follower_profile_visits else Decimal("0"),
                    cps=(follower_spend / follower_new_followers) if follower_new_followers else Decimal("0"),
                    source_file="meta-ads-api",
                    notes="Campanas follower/front-end: " + ", ".join(follower_notes[:10]),
                )
            )

        if options["sync_axis"]:
            sync = AxisSyncService()
            sync.sync_ad_spends([ad_spend])
            sync.sync_category_metrics(category_metrics)
            if follower_metrics:
                sync.sync_follower_metrics(follower_metrics)
            if comfama_spend_record:
                sync.sync_ad_spends([comfama_spend_record])
            if comfama_metrics:
                sync.sync_comfama_ad_metrics(comfama_metrics)

        self.stdout.write(
            json.dumps(
                {
                    "daily_spend": ad_spend.to_dict(),
                    "category_metrics": [item.to_dict() for item in category_metrics],
                    "follower_metrics": [item.to_dict() for item in follower_metrics],
                    "follower_debug_rows": follower_debug_rows,
                    "comfama_daily_spend": comfama_spend_record.to_dict() if comfama_spend_record else None,
                    "comfama_metrics": [item.to_dict() for item in comfama_metrics],
                    "unmatched_campaigns": unmatched_campaigns,
                },
                indent=2,
                default=str,
            )
        )
