from datetime import date
from decimal import Decimal
from io import StringIO
import json

from django.core.management import call_command
from django.test import TestCase, override_settings

from reports.integrations.mercadolibre import MercadoLibreClient
from reports.models import DailyChannelSale
from reports.services.falabella_sync import sync_orders_for_day
from reports.services.sales_dashboard import ensure_marketplace_catalogs


class MercadoLibreClientTests(TestCase):
    def test_day_bounds_use_colombia_business_day(self):
        client = MercadoLibreClient('client', 'secret', seller_id='123', local_timezone='America/Bogota')
        start, end = client.day_bounds(date(2026, 6, 3))
        self.assertEqual(start, '2026-06-03T05:00:00Z')
        self.assertEqual(end, '2026-06-04T04:59:59Z')


class FalabellaSyncTests(TestCase):
    def setUp(self):
        ensure_marketplace_catalogs()

    def test_orders_sync_is_scoped_to_marketplace_falabella(self):
        class FakeClient:
            def iter_orders_for_day(self, target_date):
                return iter([
                    {'Status': 'delivered', 'Price': '18070161', 'Items': {'Item': [{'Quantity': 2}, {'Quantity': 1}]}},
                    {'Status': 'cancelled', 'Price': '89910', 'Items': {'Item': {'Quantity': 1}}},
                ])
        payload = sync_orders_for_day(date(2026, 6, 25), client=FakeClient())
        sale = DailyChannelSale.objects.get(sale_date=date(2026, 6, 25), channel__slug='falabella')
        self.assertEqual(payload['sales_amount'], Decimal('18070161'))
        self.assertEqual(sale.business_unit.slug, 'marketplace')
        self.assertEqual(sale.order_count, 1)
        self.assertEqual(sale.units, 3)
        self.assertEqual(sale.source_file, 'falabella-api')


class MarketplaceHistoryCommandTests(TestCase):
    @override_settings(
        WOOCOMMERCE_CO_BASE_URL='https://uva.example',
        SHOPIFY_BALI_SHOP_DOMAIN='bali.myshopify.com',
        MERCADOLIBRE_CLIENT_ID='meli-client',
        MERCADOLIBRE_CLIENT_SECRET='meli-secret',
        FALABELLA_USER_ID='daniela.garcia@balisexstore.com',
        FALABELLA_API_KEY='falabella-key',
    )
    def test_marketplace_only_history_does_not_include_uva_or_bali(self):
        output = StringIO()
        call_command('sync_axis_history_range', '--date-from', '2026-06-03', '--date-to', '2026-06-04', '--marketplace', '--dry-run', stdout=output)
        payload = json.loads(output.getvalue())
        sources = {task['source'] for task in payload['tasks']}
        self.assertEqual(sources, {'mercadolibre-marketplace', 'falabella-marketplace'})
        self.assertEqual(payload['task_count'], 4)
