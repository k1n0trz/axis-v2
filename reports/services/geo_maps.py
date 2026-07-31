"""Mapas y metricas por region.

Salio de `sales_dashboard` junto con las cuatro tablas de alias y sufijos de nombres
de departamento que necesita. `geo_location_key` la usan los importadores de Meta y
Google Ads para normalizar el nombre de la region antes de guardarla.

No importa `sales_dashboard`: la dependencia va en una sola direccion, y
`build_bali_web_geo_map_data`, que el tablero de Bali usa, se reexporta desde alli.
"""
import json
import unicodedata
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.utils.text import slugify

from reports.models import DailyGeoAdMetric
from reports.services.common import ZERO, normalize_text, safe_ratio as _safe_ratio


UVA_GEO_COUNTRY_MAPS = {
    "CO": {"label": "Colombia", "geojson": "reports/maps/CO-adm1.min.geojson"},
    "EC": {"label": "Ecuador", "geojson": "reports/maps/EC-adm1.min.geojson"},
    "MX": {"label": "Mexico", "geojson": "reports/maps/MX-adm1.min.geojson"},
}


GEO_LOCATION_ALIASES = {
    "bogota": "bogota",
    "bogota-d-c": "bogota",
    "bogota-dc": "bogota",
    "distrito-capital": "bogota",
    "capital-district": "bogota",
    "bogota-capital-district": "bogota",
    "distrito-especial": "bogota",
    "mexico-city": "distrito-federal",
    "ciudad-de-mexico": "distrito-federal",
    "cdmx": "distrito-federal",
    "distrito-federal": "distrito-federal",
    "coahuila": "coahuila-de-zaragoza",
    "estado-de-mexico": "mexico",
    "edomex": "mexico",
    "nuevo-leon": "nuevo-leon",
    "manabi": "manabi",
    "santo-domingo": "santo-domingo-de-los-tsachilas",
    "santo-domingo-de-los-tsachilas": "santo-domingo-de-los-tsachilas",
}


GEO_NAME_PREFIXES = (
    "departamento-del-",
    "departamento-de-",
    "provincia-del-",
    "provincia-de-",
    "estado-del-",
    "estado-de-",
    "region-del-",
    "region-de-",
    "province-of-",
    "department-of-",
    "state-of-",
)


GEO_NAME_SUFFIXES = (
    "-departamento",
    "-department",
    "-provincia",
    "-province",
    "-estado",
    "-state",
    "-region",
)


def _strip_geo_qualifiers(key):
    current = key
    while True:
        previous = current
        for prefix in GEO_NAME_PREFIXES:
            if current.startswith(prefix) and len(current) > len(prefix):
                current = current[len(prefix):]
                break
        for suffix in GEO_NAME_SUFFIXES:
            if current.endswith(suffix) and len(current) > len(suffix):
                current = current[: -len(suffix)]
                break
        if current == previous:
            return current or key


def geo_location_key(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    key = slugify(ascii_value)
    if key in GEO_LOCATION_ALIASES:
        return GEO_LOCATION_ALIASES[key]
    stripped = _strip_geo_qualifiers(key)
    return GEO_LOCATION_ALIASES.get(stripped, stripped)


def _geo_metric_payload(row):
    return {
        "impressions": int(row.get("impressions", 0)),
        "reach": int(row.get("reach", 0)),
        "clicks": int(row.get("clicks", 0)),
        "purchases": float(row.get("purchases", 0)),
        "conversion_value": float(row.get("conversion_value", 0)),
        "spend": float(row.get("spend", 0)),
    }


def _empty_geo_totals():
    return {
        "impressions": 0,
        "reach": 0,
        "clicks": 0,
        "purchases": 0,
        "conversion_value": 0,
        "spend": 0,
    }


def _static_map_url(path):
    return f"{settings.STATIC_URL.rstrip('/')}/{path.lstrip('/')}"


def json_dumps_safe(value):
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_bali_web_geo_map_data(filters, kpis):
    code = "CO"
    config = UVA_GEO_COUNTRY_MAPS[code]
    queryset = DailyGeoAdMetric.objects.select_related("ad_platform").filter(
        business_unit__slug="bali", country__code=code,
        geo_level__in=[DailyGeoAdMetric.GeoLevel.REGION, DailyGeoAdMetric.GeoLevel.CITY],
    )
    if filters.get("date_start"):
        queryset = queryset.filter(metric_date__gte=filters["date_start"])
    if filters.get("date_end"):
        queryset = queryset.filter(metric_date__lte=filters["date_end"])
    region_totals = defaultdict(_empty_geo_totals)
    city_totals = defaultdict(_empty_geo_totals)
    region_names = {}
    city_names = {}
    platforms = set()
    latest_date = None
    for metric in queryset:
        key = geo_location_key(metric.location_key or metric.location_name)
        target = city_totals if metric.geo_level == DailyGeoAdMetric.GeoLevel.CITY else region_totals
        names = city_names if metric.geo_level == DailyGeoAdMetric.GeoLevel.CITY else region_names
        values = target[key]
        values["impressions"] += int(metric.impressions or 0)
        values["reach"] += int(metric.reach or 0)
        values["clicks"] += int(metric.clicks or 0)
        values["purchases"] += Decimal(str(metric.purchases or 0))
        values["conversion_value"] += Decimal(str(metric.conversion_value or 0))
        values["spend"] += Decimal(str(metric.spend_amount or 0))
        names.setdefault(key, metric.location_name)
        platforms.add(metric.ad_platform.name)
        if latest_date is None or metric.metric_date > latest_date:
            latest_date = metric.metric_date
    regions = []
    for key, values in region_totals.items():
        payload = _geo_metric_payload(values)
        row = {"key": key, "name": region_names.get(key, key.replace("-", " ").title())}
        row.update(payload)
        regions.append(row)
    regions.sort(key=lambda item: (item["impressions"], item["purchases"], item["spend"]), reverse=True)
    source_points = city_totals or region_totals
    source_names = city_names if city_totals else region_names
    points = []
    for key, values in source_points.items():
        purchases = float(values.get("purchases", 0))
        if purchases <= 0:
            continue
        payload = _geo_metric_payload(values)
        row = {"key": key, "name": source_names.get(key, key.replace("-", " ").title())}
        row.update(payload)
        points.append(row)
    points.sort(key=lambda item: (item["purchases"], item["conversion_value"], item["spend"]), reverse=True)
    totals_source = region_totals or city_totals
    totals = _empty_geo_totals()
    for values in totals_source.values():
        for metric_name in totals:
            totals[metric_name] += values.get(metric_name, 0)
    total_payload = _geo_metric_payload(totals)

    fallback_payload = _geo_metric_payload({
        "impressions": kpis.get("sessions_total", 0),
        "reach": kpis.get("sessions_total", 0),
        "clicks": 0,
        "purchases": kpis.get("web_orders_total", 0),
        "conversion_value": kpis.get("web_sales_total", 0),
        "spend": kpis.get("spend_total", 0),
    })
    display_totals = total_payload if any(total_payload.values()) else fallback_payload
    has_real_geo = bool(regions or points)
    return {
        "code": code,
        "label": config["label"],
        "geojson_url": _static_map_url(config["geojson"]),
        "regions": regions,
        "regions_json": json_dumps_safe(regions),
        "points": points[:12],
        "points_json": json_dumps_safe(points[:12]),
        "totals": display_totals,
        "totals_json": json_dumps_safe(display_totals),
        "has_real_geo": has_real_geo,
        "platforms": ", ".join(sorted(platforms)) if platforms else "Google Ads",
        "latest_date": latest_date.isoformat() if latest_date else "",
        "sessions_total": int(kpis.get("sessions_total", 0) or 0),
        "web_orders_total": float(kpis.get("web_orders_total", 0) or 0),
        "web_sales_total": float(kpis.get("web_sales_total", 0) or 0),
        "spend_total": float(kpis.get("spend_total", 0) or 0),
        "attribution": "Mapa ADM1: geoBoundaries. Metricas: Shopify y Google Ads sincronizados por Axis; no usa Analytics como fuente principal.",
    }


def build_uva_geo_map_data(filters, country_rows):
    rows_by_code = {row.get("code"): row for row in country_rows if row.get("code")}
    selected_country = filters.get("country")
    if selected_country in UVA_GEO_COUNTRY_MAPS:
        codes = [selected_country]
    else:
        codes = [code for code in ("CO", "EC", "MX") if code in rows_by_code] or ["CO", "EC", "MX"]

    maps = []
    for code in codes:
        config = UVA_GEO_COUNTRY_MAPS[code]
        row = rows_by_code.get(code, {})
        queryset = DailyGeoAdMetric.objects.select_related("ad_platform").filter(
            business_unit__slug="uva",
            country__code=code,
            geo_level__in=[DailyGeoAdMetric.GeoLevel.REGION, DailyGeoAdMetric.GeoLevel.CITY],
        )
        if filters.get("date_start"):
            queryset = queryset.filter(metric_date__gte=filters["date_start"])
        if filters.get("date_end"):
            queryset = queryset.filter(metric_date__lte=filters["date_end"])

        region_totals = defaultdict(_empty_geo_totals)
        city_totals = defaultdict(_empty_geo_totals)
        region_names = {}
        city_names = {}
        platforms = set()
        latest_date = None
        for metric in queryset:
            key = geo_location_key(metric.location_key or metric.location_name)
            target = city_totals if metric.geo_level == DailyGeoAdMetric.GeoLevel.CITY else region_totals
            names = city_names if metric.geo_level == DailyGeoAdMetric.GeoLevel.CITY else region_names
            values = target[key]
            values["impressions"] += int(metric.impressions or 0)
            values["reach"] += int(metric.reach or 0)
            values["clicks"] += int(metric.clicks or 0)
            values["purchases"] += Decimal(str(metric.purchases or 0))
            values["conversion_value"] += Decimal(str(metric.conversion_value or 0))
            values["spend"] += Decimal(str(metric.spend_amount or 0))
            names.setdefault(key, metric.location_name)
            platforms.add(metric.ad_platform.name)
            if latest_date is None or metric.metric_date > latest_date:
                latest_date = metric.metric_date

        regions = []
        for key, values in region_totals.items():
            payload = _geo_metric_payload(values)
            regions.append({"key": key, "name": region_names.get(key, key.replace("-", " ").title()), **payload})
        regions.sort(key=lambda item: (item["impressions"], item["purchases"]), reverse=True)

        source_points = city_totals or region_totals
        source_names = city_names if city_totals else region_names
        points = []
        for key, values in source_points.items():
            purchases = float(values.get("purchases", 0))
            if purchases <= 0:
                continue
            payload = _geo_metric_payload(values)
            points.append({"key": key, "name": source_names.get(key, key.replace("-", " ").title()), **payload})
        points.sort(key=lambda item: item["purchases"], reverse=True)

        totals = _empty_geo_totals()
        for values in region_totals.values():
            for metric_name in totals:
                totals[metric_name] += values.get(metric_name, 0)
        total_payload = _geo_metric_payload(totals)
        maps.append({
            "code": code,
            "label": config["label"],
            "geojson_url": _static_map_url(config["geojson"]),
            "regions": regions,
            "regions_json": json_dumps_safe(regions),
            "points": points[:12],
            "points_json": json_dumps_safe(points[:12]),
            "totals": total_payload,
            "totals_json": json_dumps_safe(total_payload),
            "sales": row.get("sales", 0),
            "spend": row.get("spend", 0),
            "roas": row.get("roas", 0),
            "has_real_geo": bool(regions or points),
            "platforms": ", ".join(sorted(platforms)) if platforms else "Google Ads / Meta Ads",
            "latest_date": latest_date.isoformat() if latest_date else "",
            "attribution": "Mapa ADM1: geoBoundaries. Metricas: Google Ads y Meta Ads sincronizados por Axis.",
        })
    return {
        "maps": maps,
        "selected_country": selected_country or "",
        "is_estimated": False,
    }
