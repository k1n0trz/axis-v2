from django import template
from django.db.models import Count, Max

from reports.models import AwnInternationalFollowerMetric, BaliDailyMetric, BaliPhysicalStoreSale, BaliWhatsAppSale, BusinessUnit, Channel, ComfamaSale, DailyProductCategoryMetric, DailyProductCategorySale

register = template.Library()


@register.inclusion_tag("admin/includes/admin_dashboard_cards.html")
def axis_admin_dashboard():
    latest_bali = BaliDailyMetric.objects.aggregate(date=Max("metric_date"))["date"]
    latest_whatsapp_bali = BaliWhatsAppSale.objects.aggregate(date=Max("sale_date"))["date"]
    latest_physical_bali = BaliPhysicalStoreSale.objects.aggregate(date=Max("sale_date"))["date"]
    latest_uva_categories = DailyProductCategoryMetric.objects.aggregate(date=Max("metric_date"))["date"]
    latest_uva_sales = DailyProductCategorySale.objects.aggregate(date=Max("sale_date"))["date"]
    latest_comfama = ComfamaSale.objects.aggregate(date=Max("sale_date"))["date"]
    latest_awn = AwnInternationalFollowerMetric.objects.aggregate(date=Max("metric_date"))["date"]

    cards = [
        {"label": "Marcas activas", "value": BusinessUnit.objects.filter(is_active=True).count(), "meta": "Catalogo principal de marcas"},
        {"label": "Canales activos", "value": Channel.objects.filter(is_active=True).count(), "meta": "Canales visibles en dashboards y admin"},
        {"label": "Metricas Uva por categoria", "value": DailyProductCategoryMetric.objects.count(), "meta": f"Ultima carga: {latest_uva_categories or 'Sin datos'}"},
        {"label": "Ventas WhatsApp Bali", "value": BaliWhatsAppSale.objects.count(), "meta": f"Ultima carga: {latest_whatsapp_bali or 'Sin datos'}"},
        {"label": "Tienda Fisica Bali", "value": BaliPhysicalStoreSale.objects.count(), "meta": f"Ultima carga: {latest_physical_bali or 'Sin datos'}"},
        {"label": "Metricas Bali", "value": BaliDailyMetric.objects.count(), "meta": f"Ultima carga: {latest_bali or 'Sin datos'}"},
        {"label": "Ventas Comfama", "value": ComfamaSale.objects.count(), "meta": f"Ultima carga: {latest_comfama or 'Sin datos'}"},
    ]

    adjustments = [
        "El admin conserva tema oscuro, con una portada ejecutiva y accesos mas claros.",
        "Los modulos clave quedaron en espanol y con guias de uso visibles dentro de los formularios.",
        "Bali ahora tiene modulo diario propio para Web + Google Ads y modulo dedicado para WhatsApp Bali.",
        "Las tablas priorizan filtros, fechas y trazabilidad para facilitar actualizaciones diarias.",
        "Uva, Comfama, Awn y Bali conservan lectura separada para no mezclar operaciones.",
    ]

    freshness = [
        {"label": "Uva categoria", "value": latest_uva_sales or "Sin datos"},
        {"label": "Comfama", "value": latest_comfama or "Sin datos"},
        {"label": "Awn Internacional", "value": latest_awn or "Sin datos"},
        {"label": "Bali Web", "value": latest_bali or "Sin datos"},
        {"label": "Bali WhatsApp", "value": latest_whatsapp_bali or "Sin datos"},
        {"label": "Bali Tienda Fisica", "value": latest_physical_bali or "Sin datos"},
    ]

    summary = {
        "brands_with_data": BusinessUnit.objects.annotate(total=Count("channels")).filter(is_active=True).count(),
        "daily_modules": 5,
        "guided_modules": 7,
    }

    return {"cards": cards, "adjustments": adjustments, "freshness": freshness, "summary": summary}
