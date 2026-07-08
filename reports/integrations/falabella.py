from datetime import datetime, time, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
import hashlib
import hmac
from zoneinfo import ZoneInfo

import requests


def decimal_from(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value).replace(',', ''))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _strip_namespace(tag):
    return str(tag or '').split('}')[-1]


def _xml_to_data(node):
    children = list(node)
    if not children:
        return (node.text or '').strip()
    grouped = {}
    for child in children:
        key = _strip_namespace(child.tag)
        value = _xml_to_data(child)
        if key in grouped:
            if not isinstance(grouped[key], list):
                grouped[key] = [grouped[key]]
            grouped[key].append(value)
        else:
            grouped[key] = value
    return grouped


def _as_list(value):
    if value in (None, ''):
        return []
    return value if isinstance(value, list) else [value]

class FalabellaSellerCenterClient:
    def __init__(self, base_url, user_id, api_key, timeout=45, local_timezone='America/Bogota'):
        self.base_url = str(base_url or '').strip().rstrip('/')
        self.user_id = str(user_id or '').strip()
        self.api_key = str(api_key or '').strip()
        self.timeout = timeout
        self.local_timezone = ZoneInfo(str(local_timezone or 'America/Bogota'))
        self.session = requests.Session()

    def day_bounds(self, target_date):
        start_local = datetime.combine(target_date, time.min, tzinfo=self.local_timezone)
        end_local = datetime.combine(target_date, time.max, tzinfo=self.local_timezone)
        return (
            start_local.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
            end_local.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
        )

    def signed_params(self, action, params=None):
        if not self.base_url or not self.user_id or not self.api_key:
            raise RuntimeError('Faltan FALABELLA_API_URL, FALABELLA_USER_ID y/o FALABELLA_API_KEY.')
        payload = {
            'Action': action,
            'Format': 'XML',
            'Timestamp': datetime.now(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
            'UserID': self.user_id,
            'Version': '1.0',
        }
        payload.update(params or {})
        canonical = urlencode(sorted(payload.items()))
        payload['Signature'] = hmac.new(self.api_key.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
        return payload

    def call(self, action, params=None):
        response = self.session.get(self.base_url, params=self.signed_params(action, params), timeout=self.timeout)
        if not response.ok:
            raise RuntimeError('Falabella Seller Center devolvio HTTP %s: %s' % (response.status_code, response.text[:500]))
        root = ET.fromstring(response.content)
        data = _xml_to_data(root)
        if isinstance(data, dict) and data.get('ErrorResponse'):
            raise RuntimeError('Falabella Seller Center devolvio error: %s' % data.get('ErrorResponse'))
        return data

    def iter_orders_for_day(self, target_date, limit=100):
        start, end = self.day_bounds(target_date)
        offset = 0
        while True:
            payload = self.call('GetOrders', {'CreatedAfter': start, 'CreatedBefore': end, 'Limit': str(limit), 'Offset': str(offset)})
            body = payload.get('Body', payload) if isinstance(payload, dict) else {}
            orders_node = body.get('Orders') if isinstance(body, dict) else None
            orders = _as_list((orders_node or {}).get('Order') if isinstance(orders_node, dict) else orders_node)
            if not orders:
                break
            for order in orders:
                yield order
            total = int(decimal_from(body.get('TotalCount') or body.get('Total') or offset + len(orders))) if isinstance(body, dict) else offset + len(orders)
            offset += len(orders)
            if offset >= total:
                break

    def get_order_items(self, order_id):
        payload = self.call('GetOrderItems', {'OrderId': str(order_id)})
        body = payload.get('Body', payload) if isinstance(payload, dict) else {}
        items_node = body.get('OrderItems') if isinstance(body, dict) else None
        return _as_list((items_node or {}).get('OrderItem') if isinstance(items_node, dict) else items_node)

    def iter_products(self, limit=100, max_items=None):
        offset = 0
        fetched = 0
        while True:
            payload = self.call('GetProducts', {'Limit': str(limit), 'Offset': str(offset)})
            body = payload.get('Body', payload) if isinstance(payload, dict) else {}
            products_node = body.get('Products') if isinstance(body, dict) else None
            products = _as_list((products_node or {}).get('Product') if isinstance(products_node, dict) else products_node)
            if not products:
                break
            for product in products:
                yield product
                fetched += 1
                if max_items and fetched >= max_items:
                    return
            total = int(decimal_from(body.get('TotalCount') or body.get('Total') or offset + len(products))) if isinstance(body, dict) else offset + len(products)
            offset += len(products)
            if offset >= total:
                break
