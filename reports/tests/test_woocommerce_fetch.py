import io
import json
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class WooCommerceFetchTests(SimpleTestCase):
    @patch("reports.management.commands.fetch_woocommerce_sales.WooCommerceClient")
    def test_uva_fetch_uses_woocommerce_report_total_and_reconciles_categories(self, client_class):
        client = client_class.return_value
        client.iter_orders_for_day.return_value = [
            {
                "id": 1,
                "status": "completed",
                "total": "1000",
                "shipping_total": "0",
                "line_items": [
                    {"name": "Copa Menstrual UVA", "quantity": 1, "total": "100"},
                    {"name": "Lovense Lush 4", "quantity": 1, "total": "900"},
                ],
            }
        ]
        client.get_sales_report_for_day.return_value = {
            "net_sales": "1000",
            "total_orders": 2,
            "total_items": 2,
        }
        output = io.StringIO()

        call_command(
            "fetch_woocommerce_sales",
            "--date",
            "2026-06-21",
            "--country",
            "CO",
            "--currency",
            "COP",
            "--base-url",
            "https://example.test",
            "--consumer-key",
            "key",
            "--consumer-secret",
            "secret",
            stdout=output,
        )

        payload = json.loads(output.getvalue())
        categories = {item["category_slug"]: Decimal(item["sales_amount"]) for item in payload["category_sales"]}

        self.assertEqual(Decimal(payload["channel_sale"]["sales_amount"]), Decimal("1000"))
        self.assertEqual(payload["channel_sale"]["order_count"], 2)
        self.assertEqual(payload["channel_sale"]["units"], 2)
        self.assertEqual(categories["copa-menstrual"], Decimal("100.00"))
        self.assertEqual(categories["otros-uva"], Decimal("900.00"))
        self.assertEqual(payload["debug"]["skipped_products"][0]["name"], "Lovense Lush 4")
        self.assertIn("processing", client.iter_orders_for_day.call_args.kwargs["statuses"])

    @patch("reports.management.commands.fetch_woocommerce_sales.WooCommerceClient")
    def test_mexico_category_sales_keep_original_mxn_before_cop_conversion(self, client_class):
        client = client_class.return_value
        client.iter_orders_for_day.return_value = [
            {
                "id": 1,
                "status": "completed",
                "total": "13047",
                "shipping_total": "0",
                "line_items": [
                    {
                        "name": "Copa Menstrual",
                        "quantity": 19,
                        "total": "13047",
                    }
                ],
            }
        ]
        client.get_sales_report_for_day.return_value = {
            "net_sales": "13047",
            "total_orders": 1,
            "total_items": 19,
        }
        output = io.StringIO()

        call_command(
            "fetch_woocommerce_sales",
            "--date",
            "2026-06-01",
            "--country",
            "MX",
            "--currency",
            "MXN",
            "--base-url",
            "https://example.test",
            "--consumer-key",
            "key",
            "--consumer-secret",
            "secret",
            stdout=output,
        )

        payload = json.loads(output.getvalue())
        category = payload["category_sales"][0]

        self.assertEqual(Decimal(category["exchange_rate"]), Decimal("200"))
        self.assertEqual(Decimal(category["original_amount"]), Decimal("13047.00"))
        self.assertEqual(Decimal(category["sales_amount"]), Decimal("2609400.00"))
