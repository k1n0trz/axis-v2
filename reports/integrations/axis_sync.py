from decimal import Decimal

from django.db import transaction
from django.utils.text import slugify

from reports.integrations.schema import (
    AdSpendRecord,
    BaliMetricRecord,
    CategoryMetricRecord,
    CategorySaleRecord,
    ChannelSaleRecord,
    ComfamaAdMetricRecord,
    FollowerMetricRecord,
    GeoAdMetricRecord,
)
from reports.models import (
    AdPlatform,
    AwnInternationalFollowerMetric,
    BaliDailyMetric,
    BusinessUnit,
    Channel,
    ComfamaAdMetric,
    Country,
    DailyAdSpend,
    DailyChannelSale,
    DailyGeoAdMetric,
    DailyProductCategoryMetric,
    DailyProductCategorySale,
    ProductCategory,
)
from reports.services.comfama_import import ensure_comfama_ad_catalogs
from reports.services.sales_dashboard import ensure_ad_platform_catalogs, ensure_bali_catalogs, ensure_uva_catalogs


def _business_unit(slug):
    if slug == "uva":
        ensure_uva_catalogs()
    elif slug == "bali":
        ensure_bali_catalogs()
    elif slug == "comfama-uva":
        ensure_comfama_ad_catalogs()
    return BusinessUnit.objects.get(slug=slug)


def _country(code):
    return Country.objects.get(code=code)


def _channel(unit, slug):
    channel = Channel.objects.filter(business_unit=unit, slug=slug).first()
    if channel:
        return channel
    return Channel.objects.create(
        business_unit=unit,
        slug=slug,
        name=slug.replace("-", " ").title(),
        display_order=99,
        is_active=True,
    )


def _category(category_slug, category_name):
    category = ProductCategory.objects.filter(slug=category_slug).first()
    if category:
        return category
    return ProductCategory.objects.create(
        slug=category_slug or slugify(category_name),
        name=category_name,
        description=f"Categoria creada por integracion automatizada para {category_name}.",
        is_active=True,
    )


def _platform(platform_slug):
    ensure_ad_platform_catalogs()
    return AdPlatform.objects.get(slug=platform_slug)


class AxisSyncService:
    @transaction.atomic
    def sync_channel_sales(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, ChannelSaleRecord):
                continue
            unit = _business_unit(record.business_unit_slug)
            country = _country(record.country_code)
            channel = _channel(unit, record.channel_slug)
            _, created = DailyChannelSale.objects.update_or_create(
                business_unit=unit,
                country=country,
                channel=channel,
                sale_date=record.sale_date,
                defaults={
                    "sales_amount": record.sales_amount,
                    "order_count": record.order_count,
                    "units": record.units,
                    "spend_amount": record.spend_amount,
                    "source_type": DailyChannelSale.SourceType.IMPORTED,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_category_sales(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, CategorySaleRecord):
                continue
            unit = _business_unit(record.business_unit_slug)
            country = _country(record.country_code)
            channel = _channel(unit, record.channel_slug)
            category = _category(record.category_slug, record.category_name)
            _, created = DailyProductCategorySale.objects.update_or_create(
                business_unit=unit,
                country=country,
                channel=channel,
                category=category,
                sale_date=record.sale_date,
                defaults={
                    "sales_amount": record.sales_amount,
                    "original_amount": record.original_amount,
                    "original_currency": record.original_currency,
                    "exchange_rate": record.exchange_rate,
                    "quantity": record.quantity,
                    "source_type": DailyProductCategorySale.SourceType.IMPORTED,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_ad_spends(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, AdSpendRecord):
                continue
            unit = _business_unit(record.business_unit_slug)
            country = _country(record.country_code)
            platform = _platform(record.ad_platform_slug)
            _, created = DailyAdSpend.objects.update_or_create(
                business_unit=unit,
                country=country,
                ad_platform=platform,
                spend_date=record.spend_date,
                defaults={
                    "spend_amount": record.spend_amount,
                    "source_type": DailyAdSpend.SourceType.IMPORTED,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_category_metrics(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, CategoryMetricRecord):
                continue
            unit = _business_unit(record.business_unit_slug)
            country = _country(record.country_code)
            category = _category(record.category_slug, record.category_name)
            existing = DailyProductCategoryMetric.objects.filter(
                business_unit=unit,
                country=country,
                category=category,
                metric_date=record.metric_date,
            ).first()
            defaults = {
                "cpa_meta": existing.cpa_meta if existing else None,
                "cpa_google": existing.cpa_google if existing else None,
                "spend_meta": existing.spend_meta if existing else Decimal("0"),
                "spend_google": existing.spend_google if existing else Decimal("0"),
                "sales_amount": existing.sales_amount if existing else Decimal("0"),
                "source_type": DailyProductCategoryMetric.SourceType.IMPORTED,
                "source_file": record.source_file,
                "notes": record.notes,
            }
            source_name = str(record.source_file or "").lower()
            has_meta_values = record.cpa_meta is not None or record.spend_meta or "meta" in source_name
            has_google_values = record.cpa_google is not None or record.spend_google or "google" in source_name
            if has_meta_values:
                defaults["cpa_meta"] = record.cpa_meta
                defaults["spend_meta"] = record.spend_meta
            if has_google_values:
                defaults["cpa_google"] = record.cpa_google
                defaults["spend_google"] = record.spend_google
            if record.sales_amount or not existing:
                defaults["sales_amount"] = record.sales_amount
            defaults["total_spend"] = (defaults["spend_meta"] or Decimal("0")) + (defaults["spend_google"] or Decimal("0"))
            _, created = DailyProductCategoryMetric.objects.update_or_create(
                business_unit=unit,
                country=country,
                category=category,
                metric_date=record.metric_date,
                defaults=defaults,
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_geo_ad_metrics(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, GeoAdMetricRecord):
                continue
            unit = _business_unit(record.business_unit_slug)
            country = _country(record.country_code)
            platform = _platform(record.ad_platform_slug)
            _, created = DailyGeoAdMetric.objects.update_or_create(
                business_unit=unit,
                country=country,
                ad_platform=platform,
                metric_date=record.metric_date,
                geo_level=record.geo_level,
                location_key=record.location_key,
                defaults={
                    "location_name": record.location_name,
                    "platform_location_id": record.platform_location_id,
                    "impressions": max(int(record.impressions or 0), 0),
                    "reach": max(int(record.reach or 0), 0),
                    "clicks": max(int(record.clicks or 0), 0),
                    "purchases": record.purchases or Decimal("0"),
                    "conversion_value": record.conversion_value or Decimal("0"),
                    "spend_amount": record.spend_amount or Decimal("0"),
                    "source_type": DailyGeoAdMetric.SourceType.IMPORTED,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_comfama_ad_metrics(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, ComfamaAdMetricRecord):
                continue
            category = _category(record.category_slug, record.category_name)
            _, created = ComfamaAdMetric.objects.update_or_create(
                metric_date=record.metric_date,
                category=category,
                defaults={
                    "cpl": record.cpl,
                    "spend_amount": record.spend_amount,
                    "conversations": record.conversations,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_follower_metrics(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, FollowerMetricRecord):
                continue
            country = _country(record.country_code)
            _, created = AwnInternationalFollowerMetric.objects.update_or_create(
                country=country,
                metric_date=record.metric_date,
                defaults={
                    "instagram_profile_visits": record.instagram_profile_visits,
                    "new_followers": record.new_followers,
                    "spend_amount": record.spend_amount,
                    "cpr": record.cpr,
                    "cps": record.cps,
                    "source_type": AwnInternationalFollowerMetric.SourceType.IMPORTED,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats

    @transaction.atomic
    def sync_bali_metrics(self, records):
        stats = {"created": 0, "updated": 0}
        for record in records:
            if not isinstance(record, BaliMetricRecord):
                continue
            catalogs = ensure_bali_catalogs()
            _, created = BaliDailyMetric.objects.update_or_create(
                business_unit=catalogs["business_unit"],
                country=catalogs["country"],
                metric_date=record.metric_date,
                defaults={
                    "sessions": record.sessions,
                    "web_sales_amount": record.web_sales_amount,
                    "web_order_count": record.web_order_count,
                    "google_spend_amount": record.google_spend_amount,
                    "google_attributed_orders": record.google_attributed_orders,
                    "whatsapp_conversations": record.whatsapp_conversations,
                    "cpa": record.cpa,
                    "source_type": BaliDailyMetric.SourceType.IMPORTED,
                    "source_file": record.source_file,
                    "notes": record.notes,
                },
            )
            stats["created" if created else "updated"] += 1
        return stats
