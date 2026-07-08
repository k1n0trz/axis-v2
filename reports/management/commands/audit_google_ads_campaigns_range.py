import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.integrations.clients import ExchangeRateClient, GoogleAdsClient, load_json_mapping, match_rule
from reports.management.commands.fetch_google_ads import (
    decimal_from_micros,
    fallback_uva_category,
    google_ads_credentials_configured,
    normalize_customer_id,
)
from reports.services.sales_dashboard import uva_exchange_rate_for_country


ZERO = Decimal("0")


def money(value):
    return str((value or ZERO).quantize(Decimal("0.01")))


def iter_dates(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


class Command(BaseCommand):
    help = "Audita campanas Google Ads por regla de categoria para un rango."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", required=True)
        parser.add_argument("--date-to", required=True)
        parser.add_argument("--country", default="CO")
        parser.add_argument("--customer-id", default="")
        parser.add_argument("--rules", default="docs/mappings/google-category-rules.example.json")
        parser.add_argument("--currency", default="COP")
        parser.add_argument("--target-currency", default="COP")

    def handle(self, *args, **options):
        country_code = options["country"].upper()
        customer_id = normalize_customer_id(options["customer_id"] or getattr(settings, f"GOOGLE_ADS_{country_code}_CUSTOMER_ID", ""))
        if not customer_id:
            raise CommandError("Falta el customer id de Google Ads.")
        if not google_ads_credentials_configured():
            raise CommandError("Faltan credenciales OAuth/Developer Token de Google Ads.")

        start_date = date.fromisoformat(options["date_from"])
        end_date = date.fromisoformat(options["date_to"])
        rules = load_json_mapping(options["rules"]).get("rules", []) if options["rules"] else []
        client = GoogleAdsClient(
            developer_token=getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            client_id=getattr(settings, "GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", ""),
            login_customer_id=getattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
        )
        fx = ExchangeRateClient(
            getattr(settings, "EXCHANGE_RATE_API_URL", "https://api.exchangerate.host"),
            api_key=getattr(settings, "EXCHANGE_RATE_API_KEY", ""),
        )

        raw_total = ZERO
        matched_total = ZERO
        by_campaign = defaultdict(lambda: {"spend": ZERO, "category": "", "conversions": ZERO})
        by_category = defaultdict(lambda: {"spend": ZERO, "conversions": ZERO})
        unmatched = defaultdict(lambda: {"spend": ZERO, "conversions": ZERO})

        for target_date in iter_dates(start_date, end_date):
            rows = client.search(customer_id, self._campaign_query(target_date))
            for batch in rows:
                for row in batch.get("results", []):
                    campaign_name = row["campaign"]["name"]
                    currency_code = row["customer"]["currencyCode"]
                    spend = decimal_from_micros(row["metrics"].get("costMicros"))
                    spend_cop = self._convert_spend(spend, currency_code, country_code, options["target_currency"], target_date, fx)
                    conversions = Decimal(str(row["metrics"].get("conversions") or "0"))
                    raw_total += spend_cop
                    category_slug = match_rule(campaign_name, rules) or fallback_uva_category(country_code)
                    by_campaign[campaign_name]["spend"] += spend_cop
                    by_campaign[campaign_name]["conversions"] += conversions
                    by_campaign[campaign_name]["category"] = category_slug
                    if category_slug:
                        matched_total += spend_cop
                        by_category[category_slug]["spend"] += spend_cop
                        by_category[category_slug]["conversions"] += conversions
                    else:
                        unmatched[campaign_name]["spend"] += spend_cop
                        unmatched[campaign_name]["conversions"] += conversions

        payload = {
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "country": country_code,
            "customer_id": customer_id,
            "raw_total": money(raw_total),
            "matched_total": money(matched_total),
            "unmatched_total": money(raw_total - matched_total),
            "by_category": [
                {"category": slug, "spend": money(values["spend"]), "conversions": str(values["conversions"])}
                for slug, values in sorted(by_category.items())
            ],
            "unmatched_campaigns": [
                {"campaign": name, "spend": money(values["spend"]), "conversions": str(values["conversions"])}
                for name, values in sorted(unmatched.items(), key=lambda item: item[1]["spend"], reverse=True)
                if values["spend"]
            ],
            "campaigns": [
                {
                    "campaign": name,
                    "category": values["category"],
                    "spend": money(values["spend"]),
                    "conversions": str(values["conversions"]),
                }
                for name, values in sorted(by_campaign.items(), key=lambda item: item[1]["spend"], reverse=True)
                if values["spend"]
            ],
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))

    def _campaign_query(self, target_date):
        return f"""
            SELECT
              campaign.id,
              campaign.name,
              customer.currency_code,
              metrics.cost_micros,
              metrics.conversions
            FROM campaign
            WHERE segments.date = '{target_date.isoformat()}'
        """

    def _convert_spend(self, amount, currency_code, country_code, target_currency, target_date, fx):
        if currency_code == target_currency:
            return amount
        fixed_rate = uva_exchange_rate_for_country(country_code, currency_code)
        if fixed_rate != Decimal("1"):
            return amount * fixed_rate
        return fx.convert(currency_code, target_currency, amount, target_date=target_date)
