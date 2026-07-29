import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.integrations.axis_sync import AxisSyncService
from reports.integrations.clients import ExchangeRateClient, GoogleAdsClient, load_json_mapping, match_rule
from reports.integrations.schema import AdSpendRecord, BaliMetricRecord, CategoryMetricRecord, GeoAdMetricRecord
from reports.models import BaliDailyMetric
from reports.services.sales_dashboard import geo_location_key, uva_exchange_rate_for_country


MICRO = Decimal("1000000")
ZERO = Decimal("0")


def normalize_customer_id(value):
    return re.sub(r"\D", "", str(value or ""))


def decimal_from_micros(value):
    return Decimal(str(value or "0")) / MICRO


def rounded_int(value):
    return int(Decimal(str(value or "0")).to_integral_value(rounding=ROUND_HALF_UP))


def google_ads_credentials_configured():
    return all(
        [
            getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            getattr(settings, "GOOGLE_ADS_CLIENT_ID", ""),
            getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", ""),
            getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", ""),
        ]
    )


def fallback_uva_category(country_code):
    if country_code in {"EC", "MX"}:
        return "copa-menstrual"
    return ""


class Command(BaseCommand):
    help = "Consulta Google Ads y devuelve inversion y CPA por campana/categoria."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True)
        parser.add_argument("--country", required=True)
        parser.add_argument("--customer-id", default="")
        parser.add_argument("--business-unit", default="uva")
        parser.add_argument("--rules", default="")
        parser.add_argument("--currency", default="COP")
        parser.add_argument("--target-currency", default="COP")
        parser.add_argument("--bali-whatsapp-conversion-name", default="")
        parser.add_argument("--skip-geo", action="store_true")
        parser.add_argument("--sync-axis", action="store_true")

    def handle(self, *args, **options):
        business_unit = str(options["business_unit"] or "uva").strip().lower()
        country_code = options["country"].upper()
        customer_id = normalize_customer_id(options["customer_id"] or self._default_customer_id(business_unit, country_code))
        if not customer_id:
            raise CommandError("Falta el customer id de Google Ads.")
        if not google_ads_credentials_configured():
            raise CommandError("Faltan credenciales OAuth/Developer Token de Google Ads.")

        client = GoogleAdsClient(
            developer_token=getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            client_id=getattr(settings, "GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", ""),
            login_customer_id=getattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
        )
        target_date = date.fromisoformat(options["date"])
        if business_unit == "bali":
            payload = self._build_bali_payload(client, customer_id, target_date, options)
        else:
            payload = self._build_uva_payload(client, customer_id, target_date, country_code, options)

        geo_metrics = []
        geo_error = ""
        if not options["skip_geo"]:
            try:
                geo_metrics = self._build_geo_metrics(client, customer_id, target_date, business_unit, country_code, options)
            except Exception as exc:
                geo_error = str(exc)
        payload["geo_metrics"] = geo_metrics
        payload["geo_error"] = geo_error
        payload["output"]["geo_metrics"] = [item.to_dict() for item in geo_metrics]
        payload["output"]["geo_error"] = geo_error

        if options["sync_axis"]:
            sync = AxisSyncService()
            if business_unit == "bali":
                sync.sync_bali_metrics(payload["bali_metrics"])
                sync.sync_ad_spends(payload["daily_spend_records"])
                if payload.get("geo_metrics"):
                    sync.sync_geo_ad_metrics(payload["geo_metrics"])
            else:
                sync.sync_ad_spends([payload["daily_spend"]])
                sync.sync_category_metrics(payload["category_metric_records"])
                if payload.get("geo_metrics"):
                    sync.sync_geo_ad_metrics(payload["geo_metrics"])

        self.stdout.write(json.dumps(payload["output"], indent=2, default=str))

    def _default_customer_id(self, business_unit, country_code):
        if business_unit == "bali":
            return getattr(settings, "GOOGLE_ADS_BALI_CUSTOMER_ID", "")
        return getattr(settings, f"GOOGLE_ADS_{country_code}_CUSTOMER_ID", "")

    def _convert_spend(self, amount, currency_code, country_code, target_currency, target_date):
        if currency_code == target_currency:
            return amount
        fixed_rate = uva_exchange_rate_for_country(country_code, currency_code)
        if fixed_rate != Decimal("1"):
            return amount * fixed_rate
        fx = ExchangeRateClient(
            getattr(settings, "EXCHANGE_RATE_API_URL", "https://api.exchangerate.host"),
            api_key=getattr(settings, "EXCHANGE_RATE_API_KEY", ""),
        )
        return fx.convert(currency_code, target_currency, amount, target_date=target_date)

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

    def _conversion_query(self, target_date):
        return f"""
            SELECT
              segments.conversion_action_name,
              metrics.all_conversions
            FROM customer
            WHERE segments.date = '{target_date.isoformat()}'
        """

    def _geo_query(self, target_date):
        return f"""
            SELECT
              segments.geo_target_region,
              customer.currency_code,
              metrics.cost_micros,
              metrics.impressions,
              metrics.clicks,
              metrics.conversions,
              metrics.conversions_value
            FROM geographic_view
            WHERE segments.date = '{target_date.isoformat()}'
        """

    def _geo_target_names_query(self, resource_names):
        quoted = ", ".join(f"'{name}'" for name in resource_names)
        return f"""
            SELECT
              geo_target_constant.resource_name,
              geo_target_constant.name,
              geo_target_constant.country_code,
              geo_target_constant.target_type
            FROM geo_target_constant
            WHERE geo_target_constant.resource_name IN ({quoted})
        """

    def _lookup_geo_target_names(self, client, customer_id, resource_names):
        names = {}
        resource_names = [name for name in dict.fromkeys(resource_names or []) if name]
        for index in range(0, len(resource_names), 80):
            chunk = resource_names[index:index + 80]
            if not chunk:
                continue
            for batch in client.search(customer_id, self._geo_target_names_query(chunk)):
                for row in batch.get("results", []):
                    target = row.get("geoTargetConstant") or {}
                    resource_name = target.get("resourceName")
                    if resource_name:
                        names[resource_name] = {
                            "name": target.get("name") or resource_name.rsplit("/", 1)[-1],
                            "country_code": target.get("countryCode") or "",
                            "target_type": target.get("targetType") or "",
                        }
        return names

    def _build_geo_metrics(self, client, customer_id, target_date, business_unit, country_code, options):
        rows = client.search(customer_id, self._geo_query(target_date))
        raw_rows = []
        region_resources = []
        for batch in rows:
            for row in batch.get("results", []):
                region_resource = (row.get("segments") or {}).get("geoTargetRegion") or ""
                if not region_resource:
                    continue
                raw_rows.append(row)
                region_resources.append(region_resource)
        try:
            region_lookup = self._lookup_geo_target_names(client, customer_id, region_resources)
        except Exception:
            region_lookup = {}

        records = []
        for row in raw_rows:
            segments = row.get("segments") or {}
            metrics = row.get("metrics") or {}
            customer = row.get("customer") or {}
            region_resource = segments.get("geoTargetRegion") or ""
            lookup = region_lookup.get(region_resource, {})
            location_name = lookup.get("name") or region_resource.rsplit("/", 1)[-1]
            currency_code = customer.get("currencyCode") or options["currency"]
            spend = decimal_from_micros(metrics.get("costMicros"))
            spend_cop = self._convert_spend(spend, currency_code, country_code, options["target_currency"], target_date)
            records.append(
                GeoAdMetricRecord(
                    business_unit_slug=business_unit,
                    country_code=country_code,
                    ad_platform_slug="google-ads",
                    metric_date=target_date,
                    geo_level="region",
                    location_key=geo_location_key(location_name),
                    location_name=location_name,
                    platform_location_id=region_resource,
                    impressions=rounded_int(metrics.get("impressions") or 0),
                    reach=0,
                    clicks=rounded_int(metrics.get("clicks") or 0),
                    purchases=Decimal(str(metrics.get("conversions") or "0")),
                    conversion_value=Decimal(str(metrics.get("conversionsValue") or "0")),
                    spend_amount=spend_cop,
                    source_file="google-ads-api-geo",
                    notes=f"Cuenta Google Ads {customer_id}. geographic_view por region.",
                )
            )
        return records

    def _build_uva_payload(self, client, customer_id, target_date, country_code, options):
        rules = load_json_mapping(options["rules"]).get("rules", []) if options["rules"] else []
        rows = client.search(customer_id, self._campaign_query(target_date))
        spend_total = ZERO
        spend_by_category = defaultdict(lambda: {"google": ZERO, "results": ZERO, "names": set()})

        for batch in rows:
            for row in batch.get("results", []):
                campaign_name = row["campaign"]["name"]
                category_slug = match_rule(campaign_name, rules)
                if not category_slug:
                    category_slug = fallback_uva_category(country_code)
                if not category_slug:
                    continue
                currency_code = row["customer"]["currencyCode"]
                spend = decimal_from_micros(row["metrics"].get("costMicros"))
                spend_cop = self._convert_spend(spend, currency_code, country_code, options["target_currency"], target_date)
                conversions = Decimal(str(row["metrics"].get("conversions") or "0"))
                spend_total += spend_cop
                spend_by_category[category_slug]["google"] += spend_cop
                spend_by_category[category_slug]["results"] += conversions
                spend_by_category[category_slug]["names"].add(campaign_name)

        ad_spend = AdSpendRecord(
            business_unit_slug="uva",
            country_code=country_code,
            ad_platform_slug="google-ads",
            spend_date=target_date,
            spend_amount=spend_total,
            source_file="google-ads-api",
            notes=f"Cuenta Google Ads {customer_id}.",
        )
        category_metrics = []
        for slug, values in sorted(spend_by_category.items()):
            cpa = (values["google"] / values["results"]) if values["results"] else None
            category_metrics.append(
                CategoryMetricRecord(
                    business_unit_slug="uva",
                    country_code=country_code,
                    category_slug=slug,
                    category_name=slug.replace("-", " ").title(),
                    metric_date=target_date,
                    cpa_google=cpa,
                    spend_google=values["google"],
                    source_file="google-ads-api",
                    notes="Campanas base: " + ", ".join(sorted(values["names"])),
                )
            )

        return {
            "daily_spend": ad_spend,
            "category_metric_records": category_metrics,
            "output": {
                "daily_spend": ad_spend.to_dict(),
                "category_metrics": [item.to_dict() for item in category_metrics],
            },
        }

    def _build_bali_payload(self, client, customer_id, target_date, options):
        spend_rows = client.search(customer_id, self._campaign_query(target_date))
        spend_total = ZERO
        currencies = set()
        campaign_names = set()
        total_campaign_conversions = ZERO
        for batch in spend_rows:
            for row in batch.get("results", []):
                campaign_name = row["campaign"]["name"]
                currency_code = row["customer"]["currencyCode"]
                currencies.add(currency_code)
                campaign_names.add(campaign_name)
                spend = decimal_from_micros(row["metrics"].get("costMicros"))
                spend_total += self._convert_spend(spend, currency_code, "CO", options["target_currency"], target_date)
                total_campaign_conversions += Decimal(str(row["metrics"].get("conversions") or "0"))

        conversion_name = options["bali_whatsapp_conversion_name"] or getattr(
            settings,
            "GOOGLE_ADS_BALI_WHATSAPP_CONVERSION_NAME",
            "Balisexstore - GA4 (web) boton_de_whatsapp",
        )
        conversion_rows = client.search(customer_id, self._conversion_query(target_date))
        whatsapp_conversions = ZERO
        conversion_names = set()
        normalized_target = str(conversion_name or "").strip().lower()
        for batch in conversion_rows:
            for row in batch.get("results", []):
                row_name = str(row.get("segments", {}).get("conversionActionName") or "")
                if normalized_target and normalized_target not in row_name.lower():
                    continue
                value = Decimal(str(row.get("metrics", {}).get("allConversions") or "0"))
                whatsapp_conversions += value
                conversion_names.add(row_name)

        existing_metric = BaliDailyMetric.objects.filter(
            business_unit__slug="bali",
            country__code="CO",
            metric_date=target_date,
        ).first()
        conversations = rounded_int(whatsapp_conversions)
        cpa = (spend_total / Decimal(conversations)) if conversations else ZERO
        source_file = "google-ads-api"
        if existing_metric and existing_metric.source_file:
            existing_sources = [
                part.strip()
                for part in str(existing_metric.source_file).split(";")
                if part.strip() and part.strip().lower() != "google-ads.xlsx"
            ]
            if source_file not in existing_sources:
                existing_sources.append(source_file)
            source_file = "; ".join(existing_sources)[:255]

        bali_record = BaliMetricRecord(
            business_unit_slug="bali",
            country_code="CO",
            metric_date=target_date,
            sessions=existing_metric.sessions if existing_metric else 0,
            web_sales_amount=existing_metric.web_sales_amount if existing_metric else ZERO,
            web_order_count=existing_metric.web_order_count if existing_metric else 0,
            google_spend_amount=spend_total,
            google_attributed_orders=rounded_int(total_campaign_conversions),
            whatsapp_conversations=conversations,
            cpa=cpa,
            source_file=source_file,
            notes=(
                f"Cuenta Google Ads {customer_id}. Conversion WhatsApp: {conversion_name}. "
                "Campos Shopify preservados si ya existian."
            ),
        )
        ad_spend = AdSpendRecord(
            business_unit_slug="bali",
            country_code="CO",
            ad_platform_slug="google-ads",
            spend_date=target_date,
            spend_amount=spend_total,
            source_file="google-ads-api",
            notes=f"Cuenta Google Ads {customer_id}. Sincronizado desde Google Ads API Bali.",
        )
        return {
            "bali_metrics": [bali_record],
            "daily_spend_records": [ad_spend],
            "output": {
                "daily_spend": ad_spend.to_dict(),
                "bali_metric": bali_record.to_dict(),
                "debug": {
                    "customer_id": customer_id,
                    "currencies": sorted(currencies),
                    "campaign_count": len(campaign_names),
                    "matched_conversion_actions": sorted(conversion_names),
                },
            },
        }
