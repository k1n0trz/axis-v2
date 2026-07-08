from collections import Counter
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reports.integrations.falabella import FalabellaSellerCenterClient, decimal_from
from reports.models import Channel, Country, DailyChannelSale, MarketplaceProductInventory
from reports.services.sales_dashboard import ensure_marketplace_catalogs

CANCELLED_STATUSES = {'cancelled', 'canceled', 'cancelado', 'cancelada', 'rejected'}


def configured_client():
    return FalabellaSellerCenterClient(
        base_url=getattr(settings, 'FALABELLA_API_URL', ''),
        user_id=getattr(settings, 'FALABELLA_USER_ID', ''),
        api_key=getattr(settings, 'FALABELLA_API_KEY', ''),
        local_timezone=getattr(settings, 'MARKETPLACE_API_TIME_ZONE', 'America/Bogota'),
    )


def _lookup(payload, *keys):
    for key in keys:
        current = payload
        found = True
        for part in str(key).replace('.', ' ').split():
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ''):
            return current
    return None


def _as_list(value):
    if value in (None, ''):
        return []
    return value if isinstance(value, list) else [value]


def _items(order):
    return _as_list(_lookup(order, 'Items.Item', 'OrderItems.OrderItem', 'OrderLines.OrderLine', 'Items') or [])


def _quantity(item):
    return int(decimal_from(_lookup(item, 'Quantity', 'quantity', 'Qty', 'count')) or 0)


def _order_total(order):
    total = decimal_from(_lookup(order, 'Price', 'TotalAmount', 'GrandTotal', 'OrderTotal', 'total_amount', 'total'))
    if total:
        return total
    total = Decimal('0')
    for item in _items(order):
        total += decimal_from(_lookup(item, 'PaidPrice', 'ItemPrice', 'UnitPrice', 'Price')) * (_quantity(item) or 1)
    return total

def normalize_product(product):
    external_id = str(_lookup(product, 'SellerSku', 'ShopSku', 'Sku', 'id') or '').strip()
    sku = str(_lookup(product, 'SellerSku', 'Sku', 'ShopSku') or '').strip()
    gtin = str(_lookup(product, 'Barcode', 'EAN', 'UPC', 'gtin') or '').strip()
    status = str(_lookup(product, 'Status', 'SaleStatus', 'state') or 'active').strip().lower()
    quantity = int(decimal_from(_lookup(product, 'Quantity', 'Available', 'stock', 'inventory')) or 0)
    warnings = []
    if status not in {'active', 'published', 'online', ''}:
        warnings.append('La publicacion no esta activa.')
    if quantity <= 0:
        warnings.append('La publicacion no tiene unidades disponibles.')
    if not sku:
        warnings.append('Falta SKU para cruzar inventario automaticamente.')
    if not gtin:
        warnings.append('Falta GTIN/EAN/UPC para validar identidad del producto.')
    health = MarketplaceProductInventory.HealthStatus.CRITICAL if status not in {'active', 'published', 'online', ''} else (MarketplaceProductInventory.HealthStatus.WARNING if warnings else MarketplaceProductInventory.HealthStatus.OK)
    title = str(_lookup(product, 'Name', 'Title', 'ProductName') or external_id or sku)
    return {
        'marketplace': 'falabella',
        'item_id': f'falabella:{external_id or sku}',
        'title': title[:255],
        'sku': sku[:120],
        'gtin': gtin[:80],
        'brand': str(_lookup(product, 'Brand', 'brand') or '')[:120],
        'model': str(_lookup(product, 'Model', 'PrimaryCategory', 'model') or '')[:120],
        'category_id': str(_lookup(product, 'PrimaryCategory', 'CategoryId', 'category') or '')[:80],
        'status': status[:40],
        'permalink': str(_lookup(product, 'Url', 'ProductUrl', 'permalink') or '')[:1000],
        'thumbnail_url': str(_lookup(product, 'MainImage', 'Image', 'image_url') or '')[:1000],
        'price': decimal_from(_lookup(product, 'Price', 'SalePrice')),
        'available_quantity': quantity,
        'sold_quantity': int(decimal_from(_lookup(product, 'SoldQuantity', 'units_sold')) or 0),
        'health_status': health,
        'warning_messages': warnings,
        'raw_payload': product,
        'last_synced_at': timezone.now(),
    }


def sync_inventory(client=None, max_items=None):
    client = client or configured_client()
    normalized = [normalize_product(item) for item in client.iter_products(max_items=max_items)]
    counters = Counter()
    with transaction.atomic():
        for item in normalized:
            if not item['item_id']:
                continue
            MarketplaceProductInventory.objects.update_or_create(item_id=item['item_id'], defaults=item)
            counters[item['health_status']] += 1
    return {'items_found': len(normalized), 'items_synced': sum(counters.values()), 'ok': counters[MarketplaceProductInventory.HealthStatus.OK], 'warning': counters[MarketplaceProductInventory.HealthStatus.WARNING], 'critical': counters[MarketplaceProductInventory.HealthStatus.CRITICAL]}

def sync_orders_for_day(target_date, client=None):
    client = client or configured_client()
    catalogs = ensure_marketplace_catalogs()
    business_unit = catalogs['business_unit']
    country = catalogs['countries'].get('CO') or Country.objects.get(code='CO')
    channel = catalogs['channels'].get('falabella') or Channel.objects.get(business_unit=business_unit, slug='falabella')
    sales_amount = Decimal('0')
    order_count = 0
    units = 0
    for order in client.iter_orders_for_day(target_date):
        status = str(_lookup(order, 'Statuses.Status', 'Status', 'OrderStatus', 'state') or '').strip().lower()
        if status in CANCELLED_STATUSES:
            continue
        order_id = _lookup(order, 'OrderId', 'OrderNumber', 'OrderNr')
        line_items = client.get_order_items(order_id) if order_id and hasattr(client, 'get_order_items') else _items(order)
        line_total = sum(decimal_from(_lookup(item, 'PaidPrice', 'ItemPrice', 'UnitPrice', 'Price')) for item in line_items)
        sales_amount += line_total or _order_total(order)
        order_count += 1
        units += sum((_quantity(item) or 1) for item in line_items) or 1
    with transaction.atomic():
        sale, _ = DailyChannelSale.objects.get_or_create(
            business_unit=business_unit,
            country=country,
            channel=channel,
            sale_date=target_date,
            defaults={'sales_amount': Decimal('0'), 'spend_amount': Decimal('0'), 'order_count': 0, 'units': 0},
        )
        sale.sales_amount = sales_amount
        sale.order_count = order_count
        sale.units = units
        sale.source_type = DailyChannelSale.SourceType.IMPORTED
        sale.source_file = 'falabella-api'
        sale.notes = 'Ventas importadas desde Falabella Seller Center.'
        sale.save(update_fields=['sales_amount', 'order_count', 'units', 'source_type', 'source_file', 'notes', 'updated_at'])
    return {'date': target_date.isoformat(), 'sales_amount': sales_amount, 'order_count': order_count, 'units': units}
