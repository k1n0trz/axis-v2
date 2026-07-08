from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.core.management import call_command
from django.test import TestCase
from openpyxl import Workbook

from reports.models import AdPlatform, BusinessUnit, Country, DailyAdSpend, DailyChannelSale, DailyProductCategorySale


class MexicoImportTests(TestCase):
    def _build_workbook(self, file_path):
        workbook = Workbook()
        sales_sheet = workbook.active
        sales_sheet.title = "Hoja1"
        sales_sheet.append(["Fecha", "Producto(s)", "Articulos vendidos", "Ventas netas", "Ventas COP"])
        sales_sheet.append([date(2026, 4, 1), "1x Copa Menstrual, 1x Disco Menstrual", 2, 1000, 207000])

        ads_sheet = workbook.create_sheet("Hoja2")
        ads_sheet.append(
            [
                "Fecha",
                "Producto",
                "CPA Meta Ads",
                "CPA Google Ads",
                "Inversión Meta Ads",
                "Inversión Google Ads",
                "Inversión Total",
                "Inversión total COP",
            ]
        )
        ads_sheet.append([date(2026, 4, 1), "Copa Menstrual", 78.63, 163.58, 235.9, 654, 889.9, 184209.3])
        ads_sheet.append([date(2026, 4, 1), "Disco Menstrual", 0, 0, 426.86, 0, 426.86, 88360.02])
        workbook.save(file_path)

    def test_import_aggregates_daily_spend_across_products(self):
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            self._build_workbook(temp_path)

            call_command("import_mexico_sales", str(temp_path))

            unit = BusinessUnit.objects.get(slug="uva")
            country = Country.objects.get(code="MX")
            meta = AdPlatform.objects.get(slug="meta-ads")
            google = AdPlatform.objects.get(slug="google-ads")

            meta_spend = DailyAdSpend.objects.get(
                business_unit=unit,
                country=country,
                ad_platform=meta,
                spend_date=date(2026, 4, 1),
            )
            google_spend = DailyAdSpend.objects.get(
                business_unit=unit,
                country=country,
                ad_platform=google,
                spend_date=date(2026, 4, 1),
            )
            channel_sale = DailyChannelSale.objects.get(
                business_unit=unit,
                country=country,
                sale_date=date(2026, 4, 1),
            )
            category_sales = DailyProductCategorySale.objects.filter(
                business_unit=unit,
                country=country,
                sale_date=date(2026, 4, 1),
            )

            self.assertEqual(channel_sale.sales_amount, Decimal("200000"))
            self.assertEqual(category_sales.count(), 2)
            self.assertEqual(category_sales.first().exchange_rate, Decimal("200"))
            self.assertEqual(sum((sale.sales_amount for sale in category_sales), Decimal("0")), Decimal("200000"))
            self.assertEqual(meta_spend.spend_amount.quantize(Decimal("0.01")), Decimal("132552.00"))
            self.assertEqual(google_spend.spend_amount.quantize(Decimal("0.01")), Decimal("130800.00"))
        finally:
            temp_path.unlink(missing_ok=True)
