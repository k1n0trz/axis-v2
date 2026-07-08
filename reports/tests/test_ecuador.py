from datetime import date
from decimal import Decimal

from django.test import TestCase

from reports.models import BusinessUnit, Channel, Country, DailyProductCategorySale, ProductCategory
from reports.services.sales_dashboard import build_ecuador_snapshot, uva_exchange_rate_for_country


class EcuadorSalesTests(TestCase):
    def setUp(self):
        self.unit, _ = BusinessUnit.objects.get_or_create(slug="uva", defaults={"name": "Uva"})
        self.country, _ = Country.objects.get_or_create(code="EC", defaults={"name": "Ecuador"})
        self.channel, _ = Channel.objects.get_or_create(name="WhatsApp Ecuador", slug="whatsapp-uva-ec", business_unit=self.unit)
        self.category = ProductCategory.objects.create(name="Copa Menstrual", slug="copa-menstrual", description="Test")

    def test_category_sale_converts_usd_to_cop_on_save(self):
        sale = DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.channel,
            category=self.category,
            sale_date=date(2026, 4, 23),
            original_amount=Decimal("10"),
            original_currency="USD",
            exchange_rate=Decimal("3600"),
            quantity=1,
        )

        self.assertEqual(sale.sales_amount, Decimal("36000"))

    def test_uva_ecuador_usd_import_rate_is_fixed(self):
        self.assertEqual(uva_exchange_rate_for_country("EC", "USD"), Decimal("3700"))

    def test_uva_mexico_mxn_import_rate_is_fixed(self):
        self.assertEqual(uva_exchange_rate_for_country("MX", "MXN"), Decimal("200"))

    def test_ecuador_snapshot_keeps_usd_and_cop_separate(self):
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.channel,
            category=self.category,
            sale_date=date(2026, 4, 23),
            original_amount=Decimal("10"),
            original_currency="USD",
            exchange_rate=Decimal("3600"),
            quantity=2,
        )

        snapshot = build_ecuador_snapshot({"date_start": "2026-04-01", "date_end": "2026-04-30"})

        self.assertEqual(snapshot["kpis"]["sales_total"], 36000.0)
        self.assertEqual(snapshot["kpis"]["usd_total"], 10.0)
        self.assertEqual(snapshot["kpis"]["units"], 2)
        self.assertEqual(snapshot["kpis"]["average_ticket"], 18000.0)
        self.assertEqual(snapshot["daily_series"][0]["average_ticket"], 18000.0)
