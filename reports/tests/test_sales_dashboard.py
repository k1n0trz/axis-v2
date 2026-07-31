from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase, override_settings
from openpyxl import Workbook

from reports.integrations.clients import MetaAdsClient
from reports.management.commands.import_daily_web_sales import allocate_amount_by_quantity, split_products
from reports.models import AdPlatform, BusinessUnit, Channel, Country, DailyAdSpend, DailyChannelSale, DailyProductCategoryMetric, DailyProductCategorySale, ProductCategory, SalesTransaction
from reports.services.meta_ads_panel import (
    _creative_image_url,
    _creative_text,
    _creative_video_id,
    _meta_ad_display_name,
    _meta_ad_metrics,
    _meta_row_is_comfama,
    build_uva_meta_ads_preview,
)
from reports.services.sales_dashboard import (
    build_copa_uva_country_comparison,
    build_sales_snapshot,
    build_uva_category_snapshot,
    build_uva_product_detail,
    category_slug_from_product_name,
    subtract_one_month,
    uva_category_slug_from_product_name,
)


class SalesDashboardTests(TestCase):
    def setUp(self):
        self.unit, _ = BusinessUnit.objects.get_or_create(slug="uva", defaults={"name": "Uva"})
        self.country, _ = Country.objects.get_or_create(code="CO", defaults={"name": "Colombia"})
        self.ecuador, _ = Country.objects.get_or_create(code="EC", defaults={"name": "Ecuador"})
        self.mexico, _ = Country.objects.get_or_create(code="MX", defaults={"name": "Mexico"})
        self.web, _ = Channel.objects.get_or_create(name="Ecommerce", slug="ecommerce-uva", business_unit=self.unit)
        self.whatsapp_ec, _ = Channel.objects.get_or_create(name="WhatsApp Ecuador", slug="whatsapp-uva-ec", business_unit=self.unit)

    def test_sales_snapshot_prefers_daily_web_total_over_category_subtotal(self):
        category = ProductCategory.objects.create(name="Copa Menstrual", slug="copa-menstrual", description="Test")
        DailyChannelSale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            sale_date=date(2026, 6, 1),
            sales_amount=Decimal("1000"),
            order_count=2,
            units=2,
        )
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            category=category,
            sale_date=date(2026, 6, 1),
            sales_amount=Decimal("100"),
            quantity=1,
        )

        snapshot = build_sales_snapshot({"business_unit": "uva", "country": "CO", "date_start": "2026-06-01", "date_end": "2026-06-01"})

        self.assertEqual(snapshot["kpis"]["sales_web"], 1000.0)
        self.assertEqual(snapshot["kpis"]["sales_total"], 1000.0)

    def test_subtract_one_month_keeps_same_day_when_possible(self):
        self.assertEqual(subtract_one_month(date(2026, 4, 21)), date(2026, 3, 21))

    def test_web_import_product_split_reads_multiplication_symbol_and_commas(self):
        products = split_products("2\u00d7 Cubrepezones ultradelgados Circulares - Nude, 1\u00d7 Panties Menstruales - S, Abundante")

        self.assertEqual(
            products,
            [
                ("Cubrepezones ultradelgados Circulares - Nude", 2),
                ("Panties Menstruales - S, Abundante", 1),
            ],
        )

    def test_cubrepezones_sin_adhesivo_uses_unified_category(self):
        self.assertEqual(
            category_slug_from_product_name("Cubrepezones sin adhesivos color nude"),
            "cubrepezones",
        )
        self.assertEqual(
            category_slug_from_product_name("Cubrepezones ultradelgados sin Adhesivo - Nude"),
            "cubrepezones",
        )
        self.assertEqual(category_slug_from_product_name("Cubrepezones UVA - Nude"), "cubrepezones")
        self.assertEqual(category_slug_from_product_name("Cubrepezones ultradelgados"), "cubrepezones")
        self.assertEqual(category_slug_from_product_name("Pezonera Luxury Camtoyz"), "cubrepezones")

    def test_hidratante_intimo_has_own_category(self):
        self.assertEqual(
            category_slug_from_product_name("Hidratante Intimo Uva"),
            "hidratante-intimo-uva",
        )

    def test_uva_category_classifier_rejects_foreign_brands_before_generic_keywords(self):
        self.assertEqual(
            uva_category_slug_from_product_name("Gel Lubricante Intimo Natural Elixir - 500 ML"),
            "",
        )
        self.assertEqual(
            uva_category_slug_from_product_name("Lovense Lush 4"),
            "",
        )
        self.assertEqual(
            uva_category_slug_from_product_name("Copa Menstrual UVA talla A"),
            "copa-menstrual",
        )

    def test_meta_ad_metrics_parse_insights_payload(self):
        metrics = _meta_ad_metrics(
            {
                "insights": {
                    "data": [
                        {
                            "spend": "100000",
                            "impressions": "20000",
                            "reach": "10000",
                            "clicks": "500",
                            "ctr": "2.5",
                            "actions": [{"action_type": "purchase", "value": "4"}],
                            "action_values": [{"action_type": "purchase", "value": "360000"}],
                            "cost_per_action_type": [{"action_type": "purchase", "value": "25000"}],
                            "purchase_roas": [{"action_type": "purchase", "value": "3.6"}],
                        }
                    ]
                }
            }
        )

        self.assertEqual(metrics["spend"], 100000.0)
        self.assertEqual(metrics["impressions"], 20000)
        self.assertEqual(metrics["reach"], 10000)
        self.assertEqual(metrics["clicks"], 500)
        self.assertEqual(metrics["purchases"], 4)
        self.assertEqual(metrics["cpa_purchase"], 25000.0)
        self.assertEqual(metrics["purchase_value"], 360000.0)
        self.assertEqual(metrics["roas"], 3.6)
        self.assertEqual(metrics["ctr"], 2.5)

    def test_meta_ad_metrics_derives_purchase_value_from_roas(self):
        metrics = _meta_ad_metrics(
            {
                "insights": {
                    "data": [
                        {
                            "spend": "159940",
                            "impressions": "20182",
                            "reach": "11436",
                            "clicks": "349",
                            "actions": [{"action_type": "purchase", "value": "16"}],
                            "purchase_roas": [{"action_type": "purchase", "value": "3.49"}],
                        }
                    ]
                }
            }
        )

        self.assertEqual(metrics["purchase_value"], 558190.6)
        self.assertEqual(metrics["cpa_purchase"], 9996.25)
        self.assertEqual(metrics["cpc"], 458.28)
        self.assertEqual(metrics["cpm"], 7924.88)
        self.assertEqual(metrics["frequency"], 1.76)

    def test_meta_ad_metrics_does_not_sum_duplicate_purchase_action_types(self):
        metrics = _meta_ad_metrics(
            {
                "insights": {
                    "data": [
                        {
                            "spend": "169920",
                            "impressions": "21127",
                            "reach": "11715",
                            "clicks": "361",
                            "actions": [
                                {"action_type": "purchase", "value": "4"},
                                {"action_type": "omni_purchase", "value": "4"},
                                {"action_type": "onsite_web_purchase", "value": "4"},
                                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "4"},
                            ],
                            "action_values": [
                                {"action_type": "purchase", "value": "558840"},
                                {"action_type": "omni_purchase", "value": "558840"},
                                {"action_type": "onsite_web_purchase", "value": "558840"},
                                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "558840"},
                            ],
                            "cost_per_action_type": [
                                {"action_type": "purchase", "value": "42480"},
                                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "42480"},
                            ],
                            "purchase_roas": [
                                {"action_type": "purchase", "value": "3.29"},
                                {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3.29"},
                            ],
                        }
                    ]
                }
            }
        )

        self.assertEqual(metrics["purchases"], 4)
        self.assertEqual(metrics["purchase_value"], 558840.0)
        self.assertEqual(metrics["cpa_purchase"], 42480.0)
        self.assertEqual(metrics["roas"], 3.29)

    @override_settings(META_ACCESS_TOKEN="secret-token", META_CO_ACCOUNT_ID="3473366029576347")
    def test_meta_ads_preview_builds_positive_and_negative_pacing_insights(self):
        rows = [
            {
                "id": "winner",
                "name": "05/06/26 | Post | Incomodidad",
                "effective_status": "ACTIVE",
                "created_time": "2026-06-05T12:00:00-0500",
                "creative": {"body": "Copy ganador"},
                "insights": {
                    "data": [
                        {
                            "spend": "169920",
                            "impressions": "21127",
                            "reach": "11715",
                            "clicks": "361",
                            "actions": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "4"}],
                            "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "2235360"}],
                            "purchase_roas": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "13.16"}],
                        }
                    ]
                },
            },
            {
                "id": "spender",
                "name": "16/06/26 | Reel | Sin compras",
                "effective_status": "ACTIVE",
                "created_time": "2026-06-16T12:00:00-0500",
                "creative": {"body": "Copy en prueba"},
                "insights": {
                    "data": [
                        {
                            "spend": "90000",
                            "impressions": "6000",
                            "reach": "4000",
                            "clicks": "40",
                            "actions": [],
                        }
                    ]
                },
            },
        ]

        with patch("reports.services.sales_dashboard.MetaAdsClient.get_active_ads", return_value=rows), patch(
            "reports.services.sales_dashboard.MetaAdsClient.get_ad_images_by_hashes",
            return_value={},
        ):
            preview = build_uva_meta_ads_preview({"country": "CO", "date_start": "2026-06-01", "date_end": "2026-06-17"})

        positive = preview["pacing_insights"]["positive"]
        negative = preview["pacing_insights"]["negative"]
        self.assertTrue(any("Mayor volumen" in item["title"] for item in positive))
        self.assertTrue(any("Gasto sin compras" in item["title"] for item in negative))
        self.assertTrue(all(item.get("recommendation") for item in negative))

    def test_meta_ads_client_error_does_not_expose_access_token(self):
        class Response:
            status_code = 500

            def json(self):
                return {"error": {"message": "Internal Server Error"}}

        client = MetaAdsClient("secret-token")

        with self.assertRaises(RuntimeError) as context:
            client._raise_meta_error(Response(), "consultar anuncios activos")

        message = str(context.exception)
        self.assertIn("Meta Ads devolvio HTTP 500", message)
        self.assertNotIn("secret-token", message)
        self.assertNotIn("access_token", message)

    def test_meta_ads_client_retries_active_ads_without_insights(self):
        class Response:
            def __init__(self, ok, payload=None, status_code=200):
                self.ok = ok
                self._payload = payload or {}
                self.status_code = status_code

            def json(self):
                return self._payload

        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append(params)
            if len(calls) == 1:
                return Response(False, {"error": {"message": "Internal Server Error"}}, status_code=500)
            return Response(True, {"data": [{"id": "ad-1", "name": "Activo"}]})

        client = MetaAdsClient("secret-token")
        with patch.object(client.session, "get", side_effect=fake_get):
            rows = client.get_active_ads("123", date_start=date(2026, 6, 1), date_end=date(2026, 6, 10))

        self.assertEqual(rows, [{"id": "ad-1", "name": "Activo"}])
        self.assertIn("insights.time_range", calls[0]["fields"])
        # El reintento insiste con insights y una pagina mas pequena. Antes venia sin
        # insights y con el mismo limit, y el panel quedaba con todo en cero.
        self.assertIn("insights.time_range", calls[1]["fields"])
        self.assertLess(calls[1]["limit"], calls[0]["limit"])

    def test_meta_ads_client_retries_active_ads_with_reduced_creative_fields(self):
        class Response:
            def __init__(self, ok, payload=None, status_code=200):
                self.ok = ok
                self._payload = payload or {}
                self.status_code = status_code

            def json(self):
                return self._payload

        calls = []

        def fake_get(url, params=None, timeout=None):
            fields = params["fields"] if params else ""
            calls.append(fields)
            if "object_story_spec" in fields or "title,body" in fields:
                return Response(False, {"error": {"message": "Tried accessing nonexisting field"}}, status_code=400)
            return Response(True, {"data": [{"id": "ad-1", "name": "Activo", "creative": {"id": "creative-1"}}]})

        client = MetaAdsClient("secret-token")
        with patch.object(client.session, "get", side_effect=fake_get):
            rows = client.get_active_ads("123", date_start=date(2026, 6, 1), date_end=date(2026, 6, 10))

        self.assertEqual(rows[0]["id"], "ad-1")
        self.assertGreaterEqual(len(calls), 2)
        # Termina en el creativo que conserva las imagenes, no en el minimo.
        self.assertIn("creative{id,name,thumbnail_url,image_url}", calls[-1])

    def test_meta_ads_client_fetches_all_active_ad_pages_without_limit(self):
        class Response:
            ok = True
            status_code = 200

            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append({"url": url, "params": params})
            if params:
                return Response({"data": [{"id": "ad-1"}], "paging": {"next": "https://graph.facebook.com/v20.0/page-2"}})
            return Response({"data": [{"id": "ad-2"}]})

        client = MetaAdsClient("secret-token")
        with patch.object(client.session, "get", side_effect=fake_get):
            rows = client.get_active_ads("123", limit=None)

        self.assertEqual([row["id"] for row in rows], ["ad-1", "ad-2"])
        self.assertEqual(calls[0]["params"]["limit"], 100)
        self.assertIsNone(calls[1]["params"])

    @override_settings(META_ACCESS_TOKEN="secret-token", META_CO_ACCOUNT_ID="3473366029576347")
    def test_meta_ads_preview_shows_sanitized_error_message(self):
        with patch("reports.services.sales_dashboard.MetaAdsClient.get_active_ads", side_effect=RuntimeError("access_token=secret-token")):
            preview = build_uva_meta_ads_preview({"country": "CO", "date_start": "2026-06-01", "date_end": "2026-06-10"})

        self.assertEqual(preview["ads"], [])
        self.assertIn("No fue posible cargar anuncios activos de Meta para Colombia", preview["message"])
        self.assertNotIn("secret-token", preview["message"])
        self.assertNotIn("access_token", preview["message"])

    @override_settings(META_ACCESS_TOKEN="secret-token", META_CO_ACCOUNT_ID="3473366029576347")
    def test_meta_ads_preview_defaults_to_colombia_without_country_filter(self):
        with patch("reports.services.sales_dashboard.MetaAdsClient.get_active_ads", return_value=[] ) as get_active_ads:
            preview = build_uva_meta_ads_preview({"date_start": "2026-06-01", "date_end": "2026-06-10"})

        self.assertEqual(preview["country_code"], "CO")
        self.assertEqual(preview["requires_country"], False)
        self.assertIn("Colombia", preview["country_label"])
        get_active_ads.assert_called_once()

    @override_settings(META_ACCESS_TOKEN="secret-token", META_CO_ACCOUNT_ID="3473366029576347")
    def test_meta_ads_preview_forces_iframe_preview_for_reel_without_video_id(self):
        rows = [
            {
                "id": "ad-reel-1",
                "name": "02/07/26 | Reel | Postbioticos",
                "effective_status": "ACTIVE",
                "creative": {"id": "creative-1", "name": "Creative", "thumbnail_url": "https://example.com/thumb.jpg"},
                "campaign": {"name": "Campana"},
                "adset": {"name": "Conjunto"},
            }
        ]
        with patch("reports.services.sales_dashboard.MetaAdsClient.get_active_ads", return_value=rows), patch(
            "reports.services.sales_dashboard.MetaAdsClient.get_ad_images_by_hashes",
            return_value={},
        ), patch(
            "reports.services.sales_dashboard.MetaAdsClient.get_ad_preview_iframe_src",
            return_value="https://www.facebook.com/ads/preview/ad-reel-1",
        ) as preview_src:
            preview = build_uva_meta_ads_preview({"country": "CO", "date_start": "2026-07-01", "date_end": "2026-07-09"})

        self.assertEqual(preview["ads"][0]["media_kind"], "video")
        self.assertEqual(preview["ads"][0]["preview_url"], "https://www.facebook.com/ads/preview/ad-reel-1")
        preview_src.assert_called()

    def test_meta_ad_display_name_uses_ad_name_for_dynamic_creative(self):
        row = {"name": "26/03/26 | Reel | Subsidio"}
        creative = {"name": "{{product.name}} 2026-03-26-d02cd628adf1259930792d44be82033f"}

        self.assertEqual(_meta_ad_display_name(row, creative), "26/03/26 | Reel | Subsidio")

    def test_creative_video_id_reads_asset_feed_video(self):
        creative = {
            "asset_feed_spec": {
                "videos": [
                    {
                        "video_id": "1637182023984079",
                        "thumbnail_url": "https://example.com/thumb.jpg",
                    }
                ]
            }
        }

        self.assertEqual(_creative_video_id(creative), "1637182023984079")

    def test_creative_text_reads_asset_feed_bodies(self):
        creative = {
            "asset_feed_spec": {
                "bodies": [
                    {"text": "Dile adios a la incomodidad del periodo."},
                ]
            }
        }

        self.assertEqual(_creative_text(creative, "body", "message"), "Dile adios a la incomodidad del periodo.")

    def test_meta_row_is_comfama_reads_campaign_and_adset_names(self):
        row = {
            "name": "26/03/26 | Reel | Subsidio",
            "campaign": {"name": "11/03/26 | Comfama | Panties | Valen"},
            "adset": {"name": "25/03/26 | Intereses | Mujeres | Esp"},
        }

        self.assertTrue(_meta_row_is_comfama(row))

    def test_creative_image_url_uses_resolved_asset_hash_before_thumbnail(self):
        creative = {
            "thumbnail_url": "https://example.com/tiny.jpg",
            "asset_feed_spec": {"images": [{"hash": "abc123"}]},
        }

        self.assertEqual(
            _creative_image_url(creative, image_lookup={"abc123": {"url": "https://example.com/full.jpg"}}),
            "https://example.com/full.jpg",
        )

    def test_web_import_allocation_preserves_order_total_to_cents(self):
        allocations = allocate_amount_by_quantity(Decimal("100"), [("Producto A", 1), ("Producto B", 2)])

        self.assertEqual(sum(amount for _, _, amount in allocations), Decimal("100"))
        self.assertEqual(allocations[0][2], Decimal("33.33"))
        self.assertEqual(allocations[1][2], Decimal("66.67"))

    def test_web_import_reads_wordpress_net_sales_and_counts_orders(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Hoja1"
        sheet.append(["Fecha", "Producto(s)", "Artículos vendidos", "Ventas netas", "Atribución"])
        sheet.append([date(2026, 4, 28), "2× Copa Menstrual UVA 2 talla A - No", 2, 120000, "Directo"])
        sheet.append([date(2026, 4, 28), "1× Disco Menstrual UVA - No", 1, 80000, "Fuente: Google"])

        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "wordpress.xlsx"
            workbook.save(path)
            call_command("import_daily_web_sales", str(path), "--replace-existing")

        daily_sale = DailyChannelSale.objects.get(sale_date=date(2026, 4, 28), channel=self.web)
        self.assertEqual(daily_sale.sales_amount, Decimal("200000.00"))
        self.assertEqual(daily_sale.order_count, 2)
        self.assertEqual(
            DailyProductCategorySale.objects.filter(sale_date=date(2026, 4, 28), channel=self.web).aggregate(total=Sum("sales_amount"))["total"],
            Decimal("200000"),
        )

    def test_build_sales_snapshot_groups_sales_rows(self):
        SalesTransaction.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            product_name="Copa Uva",
            origin="Pagina Web",
            sale_date=date(2026, 4, 10),
            quantity=2,
            sale_value=Decimal("120000"),
            shipping_value=Decimal("10000"),
            source_file="test.xlsx",
            source_sheet="Colombia",
            source_row=2,
        )

        snapshot = build_sales_snapshot({"date_start": "2026-04-01", "date_end": "2026-04-30"})

        self.assertEqual(snapshot["kpis"]["sales_total"], 120000.0)
        self.assertEqual(snapshot["kpis"]["sales_web"], 120000.0)
        self.assertEqual(snapshot["kpis"]["average_ticket"], 120000.0)
        april_10 = next(item for item in snapshot["combined_series"] if item["label"] == "2026-04-10")
        self.assertEqual(april_10["average_ticket"], 120000.0)
        self.assertEqual(snapshot["sales_by_unit"], [{"label": "Uva", "value": 120000.0}])
        self.assertEqual(snapshot["sales_by_channel"], [{"label": "Web", "value": 120000.0}])

    def test_marketplace_snapshot_removes_vat_without_affecting_raw_value(self):
        marketplace, _ = BusinessUnit.objects.get_or_create(slug="marketplace", defaults={"name": "Marketplace"})
        channel, _ = Channel.objects.get_or_create(
            business_unit=marketplace,
            slug="mercado-libre",
            defaults={"name": "Mercado Libre"},
        )
        DailyChannelSale.objects.create(
            business_unit=marketplace,
            country=self.country,
            channel=channel,
            sale_date=date(2026, 4, 10),
            sales_amount=Decimal("119000"),
            spend_amount=Decimal("1000"),
            order_count=1,
        )

        snapshot = build_sales_snapshot({"date_start": "2026-04-01", "date_end": "2026-04-30", "business_unit": "marketplace"})

        self.assertEqual(snapshot["kpis"]["sales_total"], 100000.0)
        self.assertEqual(snapshot["kpis"]["sales_total_with_vat"], 119000.0)
        self.assertEqual(snapshot["kpis"]["average_ticket"], 100000.0)
        self.assertEqual(snapshot["kpis"]["average_ticket_with_vat"], 119000.0)
        self.assertEqual(snapshot["kpis"]["roas"], 100.0)
        self.assertEqual(snapshot["sales_by_channel"], [{"label": "Mercadolibre", "value": 100000.0, "value_with_vat": 119000.0}])

    def test_country_comparison_includes_mexico_when_data_exists(self):
        platform = AdPlatform.objects.create(name="Meta Ads", slug="meta-ads")
        DailyAdSpend.objects.create(business_unit=self.unit, country=self.country, ad_platform=platform, spend_date=date(2026, 4, 10), spend_amount=Decimal("50000"))
        DailyAdSpend.objects.create(business_unit=self.unit, country=self.mexico, ad_platform=platform, spend_date=date(2026, 4, 10), spend_amount=Decimal("25000"))
        SalesTransaction.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            product_name="Copa Uva",
            origin="Pagina Web",
            sale_date=date(2026, 4, 10),
            quantity=1,
            sale_value=Decimal("120000"),
            shipping_value=Decimal("0"),
            source_file="test.xlsx",
            source_sheet="Colombia",
            source_row=2,
        )
        SalesTransaction.objects.create(
            business_unit=self.unit,
            country=self.mexico,
            channel=self.web,
            product_name="Copa Uva",
            origin="Pagina Web",
            sale_date=date(2026, 4, 10),
            quantity=1,
            sale_value=Decimal("90000"),
            shipping_value=Decimal("0"),
            source_file="test.xlsx",
            source_sheet="Mexico",
            source_row=3,
        )

        rows = build_copa_uva_country_comparison({"date_start": "2026-04-01", "date_end": "2026-04-30"})

        self.assertEqual([row["label"] for row in rows], ["Colombia", "Mexico"])
        self.assertEqual(rows[0]["average_ticket"], 120000.0)
        self.assertEqual(rows[1]["average_ticket"], 90000.0)

    def test_uva_category_snapshot_reads_web_and_whatsapp_sales_from_category_sales(self):
        category = ProductCategory.objects.create(name="Copa Menstrual", slug="copa-menstrual", description="Test")
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.ecuador,
            channel=self.web,
            category=category,
            sale_date=date(2026, 4, 10),
            sales_amount=Decimal("80000"),
            original_amount=Decimal("20"),
            original_currency="USD",
            exchange_rate=Decimal("4000"),
            quantity=1,
        )
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.ecuador,
            channel=self.whatsapp_ec,
            category=category,
            sale_date=date(2026, 4, 10),
            sales_amount=Decimal("40000"),
            original_amount=Decimal("10"),
            original_currency="USD",
            exchange_rate=Decimal("4000"),
            quantity=1,
        )

        snapshot = build_uva_category_snapshot({"date_start": "2026-04-01", "date_end": "2026-04-30", "country": "EC", "business_unit": "uva"})

        self.assertEqual(snapshot["cards"][0]["sales_total"], 80000.0)
        self.assertEqual(snapshot["cards"][0]["whatsapp_sales_total"], 40000.0)
        self.assertEqual(snapshot["cards"][0]["average_ticket"], 60000.0)

    def test_uva_snapshot_uses_official_web_daily_total_even_with_category_rows(self):
        valid_category = ProductCategory.objects.create(name="Copa Menstrual", slug="copa-menstrual", description="Test")
        foreign_category = ProductCategory.objects.create(name="Lovense Lush 4", slug="lovense-lush-4", description="Test")
        DailyChannelSale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            sale_date=date(2026, 6, 21),
            sales_amount=Decimal("83000000"),
            order_count=99,
            units=99,
            source_file="woocommerce-api",
        )
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            category=valid_category,
            sale_date=date(2026, 6, 21),
            sales_amount=Decimal("150000"),
            quantity=2,
            source_file="woocommerce-api",
        )
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            category=foreign_category,
            sale_date=date(2026, 6, 21),
            sales_amount=Decimal("2500000"),
            quantity=1,
            source_file="woocommerce-api",
        )

        filters = {"date_start": "2026-06-21", "date_end": "2026-06-21", "country": "CO", "business_unit": "uva"}
        snapshot = build_sales_snapshot(filters)
        category_snapshot = build_uva_category_snapshot(filters)

        self.assertEqual(snapshot["kpis"]["sales_total"], 83000000.0)
        self.assertEqual(snapshot["kpis"]["sales_web"], 83000000.0)
        self.assertEqual(snapshot["sales_by_channel"], [{"label": "Web", "value": 83000000.0}])
        self.assertEqual([card["name"] for card in category_snapshot["cards"]], ["Copa Menstrual"])

    def test_uva_product_detail_uses_category_image_sales_and_spend(self):
        category = ProductCategory.objects.create(
            name="Copa Menstrual",
            slug="copa-menstrual",
            description="Test",
            image="product_categories/copa.png",
        )
        DailyProductCategoryMetric.objects.create(
            business_unit=self.unit,
            country=self.country,
            category=category,
            metric_date=date(2026, 4, 10),
            spend_meta=Decimal("50000"),
            spend_google=Decimal("25000"),
        )
        DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            category=category,
            sale_date=date(2026, 4, 10),
            sales_amount=Decimal("150000"),
            quantity=3,
        )

        detail = build_uva_product_detail(
            {"date_start": "2026-04-01", "date_end": "2026-04-30", "country": "CO", "business_unit": "uva"},
            category.id,
        )

        self.assertEqual(detail["image_url"], "/media/product_categories/copa.png")
        self.assertEqual(detail["daily_series"][0]["sales"], 150000.0)
        self.assertEqual(detail["daily_series"][0]["spend"], 75000.0)
        self.assertEqual(detail["daily_series"][0]["roas"], 2.0)

    def test_daily_product_category_sales_accept_return_adjustments(self):
        category = ProductCategory.objects.create(name="Esterilizador", slug="esterilizador", description="Test")
        sale = DailyProductCategorySale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.web,
            category=category,
            sale_date=date(2026, 4, 22),
            sales_amount=Decimal("-99900"),
            original_amount=Decimal("-99900"),
            quantity=-1,
        )

        self.assertEqual(sale.sales_amount, Decimal("-99900"))
        self.assertEqual(sale.quantity, -1)
