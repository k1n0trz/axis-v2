from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from reports.forms import GlobalFilterForm
from reports.models import AdPlatform, BusinessUnit, Country, DailyAdSpend


class FilterValidationTests(TestCase):
    def test_global_filter_rejects_inverted_date_range(self):
        form = GlobalFilterForm(
            {
                "period_type": "custom",
                "date_start": "2026-04-23",
                "date_end": "2026-04-01",
                "time_granularity": "daily",
                "compare_mode": "previous_period",
                "business_unit": "",
                "channel": "",
                "country": "",
                "campaign_type": "",
                "product": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("La fecha inicio no puede ser posterior", str(form.errors))


class DatabaseIntegrityTests(TestCase):
    def test_daily_ad_spend_rejects_negative_amounts(self):
        unit, _ = BusinessUnit.objects.get_or_create(slug="uva", defaults={"name": "Uva"})
        country, _ = Country.objects.get_or_create(code="CO", defaults={"name": "Colombia"})
        platform = AdPlatform.objects.create(name="Meta Ads", slug="meta-ads")

        with self.assertRaises(IntegrityError):
            DailyAdSpend.objects.create(
                business_unit=unit,
                country=country,
                ad_platform=platform,
                spend_date=date(2026, 4, 22),
                spend_amount=Decimal("-1"),
            )
