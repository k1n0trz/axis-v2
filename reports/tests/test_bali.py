import json
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TestCase, override_settings
from openpyxl import Workbook

from reports.models import BaliDailyMetric, BaliWebProductDailyMetric, DailyChannelSale
from reports.management.commands.sync_axis_daily_data import Command as SyncAxisDailyDataCommand
from reports.services.sales_dashboard import build_bali_product_detail, build_bali_snapshot, ensure_bali_catalogs


class BaliSnapshotTests(TestCase):
    def setUp(self):
        catalogs = ensure_bali_catalogs()
        self.unit = catalogs["business_unit"]
        self.country = catalogs["country"]
        self.whatsapp = catalogs["channels"]["bali-whatsapp"]
        self.physical = catalogs["channels"]["bali-tienda-fisica"]

    def test_bali_snapshot_combines_web_and_whatsapp(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 4, 1),
            sessions=100,
            web_sales_amount=Decimal("1000000"),
            web_order_count=10,
            google_spend_amount=Decimal("250000"),
            google_attributed_orders=4,
            whatsapp_conversations=20,
            cpa=Decimal("62500"),
        )
        DailyChannelSale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.whatsapp,
            sale_date=date(2026, 4, 1),
            sales_amount=Decimal("300000"),
            order_count=3,
        )
        DailyChannelSale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.physical,
            sale_date=date(2026, 4, 1),
            sales_amount=Decimal("200000"),
            order_count=2,
            units=20,
        )

        snapshot = build_bali_snapshot({"date_start": "2026-04-01", "date_end": "2026-04-30"})

        self.assertEqual(snapshot["kpis"]["sales_total"], 1452100.84)
        self.assertEqual(snapshot["kpis"]["sales_total_with_vat"], 1500000.0)
        self.assertEqual(snapshot["kpis"]["web_sales_total"], 1000000.0)
        self.assertEqual(snapshot["kpis"]["web_sales_total_with_vat"], 1000000.0)
        self.assertEqual(snapshot["kpis"]["whatsapp_sales_total"], 252100.84)
        self.assertEqual(snapshot["kpis"]["whatsapp_sales_total_with_vat"], 300000.0)
        self.assertEqual(snapshot["kpis"]["physical_sales_total"], 200000.0)
        self.assertEqual(snapshot["kpis"]["sessions_total"], 100)
        self.assertEqual(snapshot["kpis"]["orders_total"], 15)
        self.assertEqual(snapshot["kpis"]["physical_visitors_total"], 20)
        self.assertEqual(snapshot["kpis"]["physical_orders_total"], 2)
        self.assertEqual(snapshot["kpis"]["average_ticket"], 96806.72)
        self.assertEqual(snapshot["kpis"]["average_ticket_with_vat"], 100000.0)
        self.assertEqual(snapshot["kpis"]["physical_conversion_rate"], 0.1)
        self.assertEqual(snapshot["kpis"]["physical_average_ticket"], 100000.0)
        self.assertEqual(snapshot["kpis"]["physical_sales_per_visitor"], 10000.0)
        self.assertEqual(snapshot["kpis"]["conversion_rate"], 0.1)
        self.assertEqual(snapshot["kpis"]["whatsapp_conversion_rate"], 0.15)
        self.assertEqual(snapshot["kpis"]["overall_conversion_rate"], 0.1071)
        self.assertEqual(snapshot["daily_series"][0]["roas"], 5.81)
        self.assertEqual(snapshot["daily_series"][0]["sessions"], 100)
        self.assertEqual(snapshot["daily_series"][0]["average_ticket"], 96806.72)
        self.assertEqual(snapshot["web_daily"][0]["roas"], 4.0)
        self.assertEqual(snapshot["kpis"]["web_roas"], 4.0)
        self.assertIn("ROAS de 4.00", " ".join(snapshot["web_insights"]))
        self.assertTrue(snapshot["data_quality"]["web_sessions_measured"])
        self.assertFalse(snapshot["data_quality"]["web_analytics_provisional"])
        self.assertEqual(snapshot["physical_daily"][0]["sales"], 200000.0)
        self.assertEqual(snapshot["physical_daily"][0]["visitors"], 20)
        self.assertEqual(snapshot["physical_daily"][0]["orders"], 2)
        self.assertEqual(snapshot["physical_daily"][0]["conversion_rate"], 0.1)

    def test_bali_snapshot_compares_kpis_with_previous_period(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 4, 10),
            sessions=50,
            web_sales_amount=Decimal("100000"),
            web_order_count=2,
            google_spend_amount=Decimal("50000"),
            google_attributed_orders=1,
            cpa=Decimal("50000"),
        )
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            sessions=100,
            web_sales_amount=Decimal("200000"),
            web_order_count=4,
            google_spend_amount=Decimal("25000"),
            google_attributed_orders=1,
            cpa=Decimal("25000"),
        )

        snapshot = build_bali_snapshot(
            {
                "date_start": "2026-05-01",
                "date_end": "2026-05-31",
                "compare_mode": "previous_period",
            }
        )

        self.assertEqual(snapshot["comparison"]["web_sales_total"]["delta_pct"], 100.0)
        self.assertEqual(snapshot["comparison"]["web_sales_total"]["direction"], "up")
        self.assertEqual(snapshot["comparison"]["web_roas"]["direction"], "up")
        self.assertEqual(snapshot["comparison"]["spend_total"]["delta_pct"], -50.0)
        self.assertEqual(snapshot["comparison"]["spend_total"]["direction"], "up")
        self.assertEqual(snapshot["comparison"]["average_cpa"]["direction"], "up")

    def test_bali_snapshot_ranks_web_products_for_selected_range(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            sessions=100,
            web_sales_amount=Decimal("500000"),
            web_order_count=5,
        )
        for metric_date, product_title, units, sales in (
            (date(2026, 5, 9), "Producto A", 1, Decimal("50000")),
            (date(2026, 5, 10), "Producto A", 3, Decimal("150000")),
            (date(2026, 5, 10), "Producto B", 5, Decimal("100000")),
        ):
            BaliWebProductDailyMetric.objects.create(
                business_unit=self.unit,
                country=self.country,
                metric_date=metric_date,
                product_title=product_title,
                net_items_sold=units,
                gross_sales=sales,
                net_sales=sales,
                total_sales=sales,
                product_image_url="https://cdn.shopify.com/producto-b.jpg" if product_title == "Producto B" else "",
            )

        snapshot = build_bali_snapshot({"date_start": "2026-05-10", "date_end": "2026-05-10"})

        self.assertEqual([row["title"] for row in snapshot["top_web_products"]], ["Producto B", "Producto A"])
        self.assertEqual(snapshot["top_web_products"][0]["units"], 5)
        self.assertEqual(snapshot["top_web_products"][0]["total_sales"], 100000.0)
        self.assertEqual(snapshot["top_web_products"][0]["total_sales_with_vat"], 100000.0)
        self.assertEqual(snapshot["top_web_products"][0]["sales_share"], 0.2)
        self.assertEqual(snapshot["top_web_products"][0]["image_url"], "https://cdn.shopify.com/producto-b.jpg")

    def test_bali_product_detail_allocates_spend_and_returns_image(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            sessions=100,
            web_sales_amount=Decimal("200000"),
            web_order_count=2,
            google_spend_amount=Decimal("100000"),
        )
        BaliWebProductDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            product_title="Producto A",
            net_items_sold=2,
            gross_sales=Decimal("100000"),
            net_sales=Decimal("100000"),
            total_sales=Decimal("100000"),
            product_image_url="https://cdn.shopify.com/producto-a.jpg",
        )
        BaliWebProductDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            product_title="Producto B",
            net_items_sold=1,
            gross_sales=Decimal("100000"),
            net_sales=Decimal("100000"),
            total_sales=Decimal("100000"),
        )

        detail = build_bali_product_detail({"date_start": "2026-05-10", "date_end": "2026-05-10"}, "Producto A")

        self.assertEqual(detail["image_url"], "https://cdn.shopify.com/producto-a.jpg")
        self.assertEqual(detail["daily_series"][0]["spend"], 50000.0)
        self.assertEqual(detail["daily_series"][0]["roas"], 2.0)
        self.assertEqual(detail["daily_series"][0]["sales_with_vat"], 100000.0)

        user = User.objects.create_user(username="bali-product-detail", password="secret", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(
            "/api/product-detail/?unit=bali&product=Producto+A&date_start=2026-05-10&date_end=2026-05-10"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Producto A")
        self.assertEqual(response.json()["image_url"], "https://cdn.shopify.com/producto-a.jpg")

    def test_bali_web_tab_renders_previous_period_comparisons(self):
        user = User.objects.create_user(username="bali-viewer", password="secret", is_staff=True)
        self.client.force_login(user)
        for metric_date, sales, orders in (
            (date(2026, 4, 10), Decimal("100000"), 2),
            (date(2026, 5, 10), Decimal("200000"), 4),
        ):
            BaliDailyMetric.objects.create(
                business_unit=self.unit,
                country=self.country,
                metric_date=metric_date,
                sessions=100,
                web_sales_amount=sales,
                web_order_count=orders,
                google_spend_amount=Decimal("25000"),
                google_attributed_orders=1,
                cpa=Decimal("25000"),
            )
        BaliWebProductDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            product_title="Producto Destacado",
            net_items_sold=4,
            gross_sales=Decimal("220000"),
            net_sales=Decimal("200000"),
            total_sales=Decimal("200000"),
            product_image_url="https://cdn.shopify.com/producto-destacado.jpg",
        )

        response = self.client.get(
            "/bali/?period_type=custom&date_start=2026-05-01&date_end=2026-05-31"
            "&compare_mode=previous_period&business_unit=bali&country=CO&tab=web"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vs. periodo anterior")
        self.assertContains(response, "bali-comparison up")
        self.assertContains(response, "Inversion Google Ads")
        self.assertContains(response, "ROAS Web")
        self.assertContains(response, "Top 20 productos vendidos")
        self.assertContains(response, "Producto Destacado")
        self.assertContains(response, "4 unidades netas vendidas")
        self.assertContains(response, 'src="https://cdn.shopify.com/producto-destacado.jpg"')

    def test_bali_marks_rest_sales_without_sessions_as_provisional(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 10),
            sessions=0,
            web_sales_amount=Decimal("25859422"),
            web_order_count=211,
            google_spend_amount=Decimal("9173374"),
            source_file="orders-api; google-ads.xlsx",
        )

        snapshot = build_bali_snapshot({"date_start": "2026-05-01", "date_end": "2026-05-26"})

        self.assertFalse(snapshot["data_quality"]["web_sessions_measured"])
        self.assertTrue(snapshot["data_quality"]["web_analytics_provisional"])

        user = User.objects.create_user(username="bali-quality", password="secret", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(
            "/bali/?period_type=custom&date_start=2026-05-01&date_end=2026-05-26"
            "&business_unit=bali&country=CO&tab=web"
        )

        self.assertContains(response, "Datos Web provisionales")
        self.assertContains(response, '<div class="kpi-value">Sin dato</div>', count=2, html=True)

    def test_bali_identifies_partial_analytics_coverage_by_date(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 21),
            sessions=1200,
            web_sales_amount=Decimal("500000"),
            web_order_count=5,
            source_file="shopifyql",
        )
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 22),
            sessions=0,
            web_sales_amount=Decimal("300000"),
            web_order_count=3,
            source_file="orders-api",
        )
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 23),
            sessions=900,
            web_sales_amount=Decimal("200000"),
            web_order_count=2,
            source_file="orders-api; shopifyql; google-ads.xlsx",
        )

        snapshot = build_bali_snapshot({"date_start": "2026-05-21", "date_end": "2026-05-27"})

        self.assertTrue(snapshot["data_quality"]["web_analytics_provisional"])
        self.assertTrue(snapshot["data_quality"]["web_analytics_mixed"])
        self.assertEqual(snapshot["data_quality"]["web_provisional_dates"], ["22/05/2026"])

        user = User.objects.create_user(username="bali-partial", password="secret", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(
            "/bali/?period_type=custom&date_start=2026-05-21&date_end=2026-05-27"
            "&business_unit=bali&country=CO&tab=web"
        )

        self.assertContains(response, "Cobertura parcial de Shopify Analytics")
        self.assertContains(response, "22/05/2026")
        self.assertNotContains(response, "Shopify Analytics no fue cargado en este rango")


class BaliImportTests(TestCase):
    def test_import_bali_workbook_creates_daily_metrics_and_prorated_whatsapp_sales(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "bali.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Hoja1"
            sheet.append(["Fecha", "Sesiones", "Ventas web", "Pedidos web", "Inversion Google Ads", "CPA", "Conversaciones Gads", "Pedidos Gads"])
            sheet.append([date(2026, 4, 1), 100, 1000000, 10, 250000, 62500, 20, 4])
            sheet.append([date(2026, 4, 2), 80, 500000, 5, 200000, 50000, 10, 4])
            sheet2 = workbook.create_sheet("Hoja2")
            sheet2.append(["Ventas WhatsApp Abril", ""])
            sheet2.append(["Pedidos", "Ventas"])
            sheet2.append([5, 300000])
            workbook.save(temp_path)

            call_command("import_bali_sales", str(temp_path))

        self.assertEqual(BaliDailyMetric.objects.count(), 2)
        self.assertEqual(DailyChannelSale.objects.filter(channel__slug="bali-whatsapp").count(), 2)
        self.assertEqual(
            DailyChannelSale.objects.filter(channel__slug="bali-whatsapp").aggregate(total=Sum("order_count"))["total"],
            5,
        )
        self.assertEqual(
            DailyChannelSale.objects.filter(channel__slug="bali-whatsapp").aggregate(total=Sum("sales_amount"))["total"],
            Decimal("300000"),
        )


class BaliSyncCommandTests(TestCase):
    def setUp(self):
        catalogs = ensure_bali_catalogs()
        self.unit = catalogs["business_unit"]
        self.country = catalogs["country"]

    def test_shopify_sync_preserves_existing_google_ads_fields_when_not_passed(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 13),
            sessions=1368,
            web_sales_amount=Decimal("576710.00"),
            web_order_count=3,
            google_spend_amount=Decimal("371598.00"),
            google_attributed_orders=1,
            whatsapp_conversations=20,
            cpa=Decimal("371598.00"),
            source_file="google-ads.xlsx",
        )

        with patch("reports.management.commands.fetch_shopify_bali.ShopifyClient") as client_cls:
            client = client_cls.return_value
            client.get_orders_for_day.return_value = []
            client.shopifyql_query.return_value = {
                "rows": [
                    {
                        "total_sales": "600000.00",
                        "orders": 4,
                        "sessions": 1500,
                    }
                ]
            }
            call_command(
                "fetch_shopify_bali",
                "--date",
                "2026-05-13",
                "--shop-domain",
                "bali-example.myshopify.com",
                "--access-token",
                "token",
                "--sync-axis",
                stdout=StringIO(),
            )

        metric = BaliDailyMetric.objects.get(metric_date=date(2026, 5, 13))
        self.assertEqual(metric.sessions, 1500)
        self.assertEqual(metric.web_sales_amount, Decimal("600000.00"))
        self.assertEqual(metric.web_order_count, 4)
        self.assertEqual(metric.google_spend_amount, Decimal("371598.00"))
        self.assertEqual(metric.google_attributed_orders, 1)
        self.assertEqual(metric.whatsapp_conversations, 20)
        self.assertEqual(metric.cpa, Decimal("371598.00"))
        self.assertIn("google-ads.xlsx", metric.source_file)

    def test_shopify_sync_replaces_previous_orders_api_marker_when_analytics_succeeds(self):
        BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 26),
            sessions=0,
            web_sales_amount=Decimal("100000"),
            web_order_count=1,
            google_spend_amount=Decimal("35000"),
            source_file="orders-api; google-ads.xlsx",
        )

        with patch("reports.management.commands.fetch_shopify_bali.ShopifyClient") as client_cls:
            client = client_cls.return_value
            client.shopifyql_query.side_effect = [
                {"rows": [{"total_sales": "200000.00", "orders": 2, "sessions": 300}]},
                {"rows": []},
            ]
            client.product_images_by_title.return_value = {}
            call_command(
                "fetch_shopify_bali",
                "--date",
                "2026-05-26",
                "--shop-domain",
                "bali-example.myshopify.com",
                "--access-token",
                "token",
                "--sync-axis",
                stdout=StringIO(),
            )

        metric = BaliDailyMetric.objects.get(metric_date=date(2026, 5, 26))
        self.assertEqual(metric.source_file, "google-ads.xlsx; shopifyql")
        self.assertNotIn("orders-api", metric.source_file)

    def test_shopify_sync_accepts_negative_net_sales_from_analytics(self):
        with patch("reports.management.commands.fetch_shopify_bali.ShopifyClient") as client_cls:
            client_cls.return_value.shopifyql_query.return_value = {
                "rows": [
                    {
                        "total_sales": "-1098840.00",
                        "orders": 12,
                        "sessions": 1116,
                    }
                ]
            }
            call_command(
                "fetch_shopify_bali",
                "--date",
                "2026-05-04",
                "--shop-domain",
                "bali-example.myshopify.com",
                "--access-token",
                "token",
                "--sync-axis",
                stdout=StringIO(),
            )

        metric = BaliDailyMetric.objects.get(metric_date=date(2026, 5, 4))
        self.assertEqual(metric.web_sales_amount, Decimal("-1098840.00"))
        self.assertEqual(metric.sessions, 1116)
        self.assertEqual(metric.source_file, "shopifyql")

    def test_shopify_sync_stores_product_analytics_for_cards(self):
        with patch("reports.management.commands.fetch_shopify_bali.ShopifyClient") as client_cls:
            client = client_cls.return_value
            client.product_images_by_title.return_value = {
                "producto uno": "https://cdn.shopify.com/producto-uno.jpg",
            }
            client.shopifyql_query.side_effect = [
                {"rows": [{"total_sales": "450000.00", "orders": 2, "sessions": 100}]},
                {
                    "rows": [
                        {
                            "product_title": "Producto Uno",
                            "net_items_sold": "2",
                            "gross_sales": "500000.00",
                            "discounts": "-50000.00",
                            "returns": "0",
                            "net_sales": "450000.00",
                            "total_sales": "450000.00",
                        },
                        {"product_title": None, "net_items_sold": "0", "total_sales": "10000.00"},
                    ]
                },
            ]
            call_command(
                "fetch_shopify_bali",
                "--date",
                "2026-05-13",
                "--shop-domain",
                "bali-example.myshopify.com",
                "--access-token",
                "token",
                "--sync-axis",
                stdout=StringIO(),
            )

        product = BaliWebProductDailyMetric.objects.get(metric_date=date(2026, 5, 13))
        self.assertEqual(product.product_title, "Producto Uno")
        self.assertEqual(product.net_items_sold, 2)
        self.assertEqual(product.discounts, Decimal("-50000.00"))
        self.assertEqual(product.total_sales, Decimal("450000.00"))
        self.assertEqual(product.product_image_url, "https://cdn.shopify.com/producto-uno.jpg")

    def test_shopify_sync_does_not_store_orders_fallback_without_explicit_opt_in(self):
        existing = BaliDailyMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            metric_date=date(2026, 5, 13),
            sessions=1500,
            web_sales_amount=Decimal("600000.00"),
            web_order_count=4,
            source_file="shopifyql",
        )

        with patch("reports.management.commands.fetch_shopify_bali.ShopifyClient") as client_cls:
            client = client_cls.return_value
            client.shopifyql_query.side_effect = RuntimeError("Access denied for shopifyqlQuery field.")

            with self.assertRaises(CommandError):
                call_command(
                    "fetch_shopify_bali",
                    "--date",
                    "2026-05-13",
                    "--shop-domain",
                    "bali-example.myshopify.com",
                    "--access-token",
                    "token",
                    "--sync-axis",
                    stdout=StringIO(),
                )

        client.get_orders_for_day.assert_not_called()
        existing.refresh_from_db()
        self.assertEqual(existing.web_sales_amount, Decimal("600000.00"))
        self.assertEqual(existing.sessions, 1500)

    @override_settings(
        WOOCOMMERCE_CO_BASE_URL="",
        WOOCOMMERCE_MX_BASE_URL="",
        ONEDRIVE_WHATSAPP_FILE_PATH="",
        ONEDRIVE_ECUADOR_FILE_PATH="",
        ONEDRIVE_SHARED_SALES_FILE_PATH="",
        ONEDRIVE_SHARED_COMFAMA_FILE_PATH="",
        ONEDRIVE_GOOGLE_ADS_FILE_PATH="axis/google-ads.xlsx",
        ONEDRIVE_AWARENESS_FILE_PATH="",
        META_CO_ACCOUNT_ID="",
        META_MX_ACCOUNT_ID="",
        META_EC_ACCOUNT_ID="",
        GOOGLE_ADS_CO_CUSTOMER_ID="",
        GOOGLE_ADS_MX_CUSTOMER_ID="",
        GOOGLE_ADS_EC_CUSTOMER_ID="",
        SHOPIFY_BALI_SHOP_DOMAIN="bali.example",
        META_REPORTS_IMAP_HOST="",
        META_REPORTS_IMAP_USERNAME="",
        META_REPORTS_IMAP_PASSWORD="",
    )
    @override_settings(GOOGLE_ADS_BALI_CUSTOMER_ID="4042093126", SHOPIFY_BALI_SHOP_DOMAIN="bali.example")
    def test_la_pauta_de_bali_se_importa_despues_de_sus_ventas(self):
        """Primero Shopify, despues Google Ads: el ROAS necesita la venta cargada.

        Antes la referencia era "OneDrive Google Ads Workbook", que ya no existe como
        tarea: Google Ads entra por API.
        """
        tasks = SyncAxisDailyDataCommand()._build_tasks(
            date(2026, 5, 13),
            {"meta_rules": "docs/mappings/meta-category-rules.example.json", "google_rules": "docs/mappings/google-category-rules.json"},
        )
        names = [task["name"] for task in tasks]

        self.assertLess(names.index("Shopify Bali"), names.index("Google Ads Bali"))

    @override_settings(
        WOOCOMMERCE_CO_BASE_URL="",
        WOOCOMMERCE_MX_BASE_URL="",
        ONEDRIVE_WHATSAPP_FILE_PATH="",
        ONEDRIVE_ECUADOR_FILE_PATH="",
        ONEDRIVE_SHARED_SALES_FILE_PATH="",
        ONEDRIVE_SHARED_COMFAMA_FILE_PATH="",
        ONEDRIVE_GOOGLE_ADS_FILE_PATH="axis/google-ads.xlsx",
        ONEDRIVE_AWARENESS_FILE_PATH="",
        META_CO_ACCOUNT_ID="",
        META_MX_ACCOUNT_ID="",
        META_EC_ACCOUNT_ID="",
        GOOGLE_ADS_CO_CUSTOMER_ID="",
        GOOGLE_ADS_MX_CUSTOMER_ID="",
        GOOGLE_ADS_EC_CUSTOMER_ID="",
        SHOPIFY_BALI_SHOP_DOMAIN="bali.example",
        META_REPORTS_IMAP_HOST="",
        META_REPORTS_IMAP_USERNAME="",
        META_REPORTS_IMAP_PASSWORD="",
    )
    def test_daily_sync_lookback_repeats_date_scoped_tasks_once_per_day(self):
        tasks = SyncAxisDailyDataCommand()._build_tasks_for_dates(
            [date(2026, 5, 13), date(2026, 5, 14)],
            {"meta_rules": "docs/mappings/meta-category-rules.example.json", "google_rules": "docs/mappings/google-category-rules.example.json"},
        )
        names = [task["name"] for task in tasks]
        shopify_dates = [
            task["command"][task["command"].index("--date") + 1]
            for task in tasks
            if task["name"] == "Shopify Bali"
        ]

        self.assertEqual(shopify_dates, ["2026-05-13", "2026-05-14"])
        # La propiedad que importa: una tarea que no depende de la fecha no se repite
        # por dia. Antes se fijaba usando "OneDrive Google Ads Workbook" como sujeto,
        # y esa tarea ya no existe porque Google Ads entra por API.
        sin_fecha = [task["name"] for task in tasks if "--date" not in task["command"]]
        self.assertEqual(sorted(sin_fecha), sorted(set(sin_fecha)))

    @override_settings(
        WOOCOMMERCE_CO_BASE_URL="",
        WOOCOMMERCE_MX_BASE_URL="",
        ONEDRIVE_WHATSAPP_FILE_PATH="",
        ONEDRIVE_ECUADOR_FILE_PATH="",
        ONEDRIVE_SHARED_SALES_FILE_PATH="",
        ONEDRIVE_GOOGLE_ADS_FILE_PATH="axis/google-ads.xlsx",
        ONEDRIVE_AWARENESS_FILE_PATH="",
        META_CO_ACCOUNT_ID="",
        META_MX_ACCOUNT_ID="",
        META_EC_ACCOUNT_ID="",
        GOOGLE_ADS_CO_CUSTOMER_ID="123",
        GOOGLE_ADS_MX_CUSTOMER_ID="456",
        GOOGLE_ADS_EC_CUSTOMER_ID="789",
        SHOPIFY_BALI_SHOP_DOMAIN="",
    )
    def test_history_sync_uses_onedrive_google_ads_workbook_once(self):
        output = StringIO()
        call_command(
            "sync_axis_history_range",
            "--date-from",
            "2026-05-01",
            "--date-to",
            "2026-05-03",
            "--uva-ads",
            "--dry-run",
            stdout=output,
        )
        tasks = json.loads(output.getvalue())["tasks"]
        sources = [task["source"] for task in tasks]

        self.assertEqual(sources.count("onedrive-google-ads-workbook"), 1)
        self.assertNotIn("google-co", sources)
