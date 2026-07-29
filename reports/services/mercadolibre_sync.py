from collections import Counter
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reports.integrations.mercadolibre import MercadoLibreClient, decimal_from
from reports.models import BusinessUnit, Channel, Country, DailyChannelSale, MarketplaceProductInventory
from reports.services.sales_dashboard import ensure_marketplace_catalogs

SKU_ATTRIBUTE_IDS = {"SELLER_SKU", "SKU", "MODEL", "REFERENCE_CODE", "PART_NUMBER", "MPN"}
GTIN_ATTRIBUTE_IDS = {"GTIN", "EAN", "UPC", "ISBN"}


def configured_client():
    return MercadoLibreClient(
        client_id=getattr(settings, "MERCADOLIBRE_CLIENT_ID", ""),
        client_secret=getattr(settings, "MERCADOLIBRE_CLIENT_SECRET", ""),
        base_url=getattr(settings, "MERCADOLIBRE_API_URL", "https://api.mercadolibre.com"),
        seller_id=getattr(settings, "MERCADOLIBRE_SELLER_ID", ""),
        access_token=getattr(settings, "MERCADOLIBRE_ACCESS_TOKEN", ""),
        local_timezone=getattr(settings, "MARKETPLACE_API_TIME_ZONE", "America/Bogota"),
    )


def normalize_item(item):
    attrs = {str(attr.get("id") or "").upper(): str(attr.get("value_name") or attr.get("value_id") or "").strip() for attr in item.get("attributes") or []}
    sku = str(item.get("seller_custom_field") or "").strip()
    if not sku:
        sku = next((attrs[key] for key in SKU_ATTRIBUTE_IDS if attrs.get(key)), "")
    gtin = next((attrs[key] for key in GTIN_ATTRIBUTE_IDS if attrs.get(key)), "")
    pictures = item.get("pictures") or []
    thumbnail = item.get("secure_thumbnail") or item.get("thumbnail") or ""
    if not thumbnail and pictures:
        thumbnail = pictures[0].get("secure_url") or pictures[0].get("url") or ""

    warnings = []
    status = str(item.get("status") or "").strip()
    quantity = int(item.get("available_quantity") or 0)
    if status != "active":
        warnings.append("La publicacion no esta activa.")
    if quantity <= 0:
        warnings.append("La publicacion no tiene unidades disponibles.")
    if not sku:
        warnings.append("Falta SKU para cruzar inventario automaticamente.")
    if not gtin:
        warnings.append("Falta GTIN/EAN/UPC para validar identidad del producto.")

    if status != "active":
        health = MarketplaceProductInventory.HealthStatus.CRITICAL
    elif quantity <= 0 or not sku or not gtin:
        health = MarketplaceProductInventory.HealthStatus.WARNING
    else:
        health = MarketplaceProductInventory.HealthStatus.OK

    return {
        "marketplace": "mercadolibre",
        "item_id": str(item.get("id") or ""),
        "title": str(item.get("title") or "")[:255],
        "sku": sku[:120],
        "gtin": gtin[:80],
        "brand": attrs.get("BRAND", "")[:120],
        "model": attrs.get("MODEL", "")[:120],
        "category_id": str(item.get("category_id") or "")[:80],
        "status": status[:40],
        "permalink": str(item.get("permalink") or "")[:1000],
        "thumbnail_url": str(thumbnail or "")[:1000],
        "price": decimal_from(item.get("price")),
        "available_quantity": quantity,
        "sold_quantity": int(item.get("sold_quantity") or 0),
        "health_status": health,
        "warning_messages": warnings,
        "raw_payload": item,
        "last_synced_at": timezone.now(),
    }


def sync_inventory(client=None, max_items=None, status="active"):
    client = client or configured_client()
    item_ids = list(client.iter_item_ids(status=status, max_items=max_items))
    normalized = [normalize_item(item) for item in client.get_items(item_ids)]
    counters = Counter()
    with transaction.atomic():
        for item in normalized:
            if not item["item_id"]:
                continue
            MarketplaceProductInventory.objects.update_or_create(
                item_id=item["item_id"],
                defaults=item,
            )
            counters[item["health_status"]] += 1
    return {
        "items_found": len(item_ids),
        "items_synced": sum(counters.values()),
        "ok": counters[MarketplaceProductInventory.HealthStatus.OK],
        "warning": counters[MarketplaceProductInventory.HealthStatus.WARNING],
        "critical": counters[MarketplaceProductInventory.HealthStatus.CRITICAL],
    }


def sync_orders_for_day(target_date, client=None):
    client = client or configured_client()
    catalogs = ensure_marketplace_catalogs()
    business_unit = catalogs["business_unit"]
    country = catalogs["countries"].get("CO") or Country.objects.get(code="CO")
    channel = catalogs["channels"].get("mercado-libre") or Channel.objects.get(business_unit=business_unit, slug="mercado-libre")

    sales_amount = Decimal("0")
    order_count = 0
    units = 0
    for order in client.iter_orders_for_day(target_date):
        status = str(order.get("status") or "").lower()
        if status in {"cancelled", "canceled"}:
            continue
        sales_amount += decimal_from(order.get("paid_amount") or order.get("total_amount"))
        order_count += 1
        for line in order.get("order_items") or []:
            units += int(line.get("quantity") or 0)

    with transaction.atomic():
        sale, _ = DailyChannelSale.objects.get_or_create(
            business_unit=business_unit,
            country=country,
            channel=channel,
            sale_date=target_date,
            defaults={"sales_amount": Decimal("0"), "spend_amount": Decimal("0"), "order_count": 0, "units": 0},
        )
        preserved_existing_sales = False
        if not sales_amount and not order_count and not units and (sale.sales_amount or sale.order_count or sale.units):
            preserved_existing_sales = True
            sale.notes = "Mercado Libre no devolvio ventas para este dia; se conservaron ventas/pedidos/unidades existentes."
        else:
            sale.sales_amount = sales_amount
            sale.order_count = order_count
            sale.units = units
            sale.notes = "Ventas importadas desde Mercado Libre. La inversion publicitaria se conserva para carga manual."
        sale.source_type = DailyChannelSale.SourceType.IMPORTED
        sale.source_file = "mercadolibre-api"
        sale.save(update_fields=["sales_amount", "order_count", "units", "source_type", "source_file", "notes", "updated_at"])
    return {"date": target_date.isoformat(), "sales_amount": sales_amount, "order_count": order_count, "units": units, "preserved_existing_sales": preserved_existing_sales}
