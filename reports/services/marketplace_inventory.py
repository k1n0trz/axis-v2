from django.db.models import Count, Max, Q, Sum

from reports.models import MarketplaceProductInventory


def marketplace_inventory_snapshot(limit=24, marketplace="mercadolibre"):
    marketplace = str(marketplace or "mercadolibre").strip().lower()
    qs = MarketplaceProductInventory.objects.filter(marketplace=marketplace)
    totals = qs.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status="active")),
        with_stock=Count("id", filter=Q(available_quantity__gt=0)),
        zero_stock=Count("id", filter=Q(available_quantity__lte=0)),
        missing_sku=Count("id", filter=Q(sku="")),
        missing_gtin=Count("id", filter=Q(gtin="")),
        warning=Count("id", filter=Q(health_status="warning")),
        critical=Count("id", filter=Q(health_status="critical")),
        available_units=Sum("available_quantity"),
        last_synced=Max("last_synced_at"),
    )
    rows = list(
        qs.order_by("health_status", "status", "sku", "title").values(
            "item_id",
            "title",
            "sku",
            "gtin",
            "brand",
            "model",
            "status",
            "permalink",
            "thumbnail_url",
            "price",
            "available_quantity",
            "sold_quantity",
            "health_status",
            "warning_messages",
        )[:limit]
    )
    labels = {"mercadolibre": "Mercado Libre", "falabella": "Falabella"}
    return {"totals": totals, "rows": rows, "marketplace": marketplace, "label": labels.get(marketplace, marketplace.title())}
