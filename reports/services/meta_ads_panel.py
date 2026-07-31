"""Panel de anuncios activos de Meta Ads.

Salio de `sales_dashboard`, que tenia 3.726 lineas. Son 22 funciones que nada mas en
el proyecto usaba: el analisis previo confirmo cero referencias de vuelta desde el
resto del modulo, asi que la extraccion es en una sola direccion.

Aqui vive tambien la logica de metricas que se perdia en silencio cuando Meta
respondia "Please reduce the amount of data": ver `_meta_insight_payload` y el
`metrics_unavailable` que arma `build_uva_meta_ads_preview`.
"""
import logging
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from reports.integrations.clients import MetaAdsClient
from reports.models import Country
from reports.services.common import (
    ZERO,
    format_cop,
    normalize_text,
    parse_filter_date as _parse_filter_date,
    safe_ratio as _safe_ratio,
    setting_int as _setting_int,
)
from reports.utils.numbers import parse_decimal, parse_quantity

logger = logging.getLogger(__name__)


def _nested_lookup(payload, *keys):
    value = payload or {}
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return value or ""


def _creative_image_hashes(creative):
    if not isinstance(creative, dict):
        return []
    hashes = []
    if creative.get("image_hash"):
        hashes.append(creative["image_hash"])
    asset_feed = creative.get("asset_feed_spec") or {}
    images = asset_feed.get("images") if isinstance(asset_feed, dict) else None
    if isinstance(images, list):
        for image in images:
            image_hash = (image or {}).get("hash")
            if image_hash:
                hashes.append(image_hash)
    return hashes


def _creative_image_url(creative, image_lookup=None):
    if not isinstance(creative, dict):
        return ""
    if creative.get("image_url"):
        return creative["image_url"]
    image_lookup = image_lookup or {}
    for image_hash in _creative_image_hashes(creative):
        resolved = image_lookup.get(image_hash) or {}
        if resolved.get("url"):
            return resolved["url"]
    if creative.get("thumbnail_url"):
        return creative["thumbnail_url"]
    asset_feed = creative.get("asset_feed_spec") or {}
    images = asset_feed.get("images") if isinstance(asset_feed, dict) else None
    if isinstance(images, list) and images:
        first = images[0] or {}
        return first.get("url") or first.get("hash") or ""
    return ""


def _creative_video_assets(creative):
    if not isinstance(creative, dict):
        return []

    videos = []
    story = creative.get("object_story_spec") or {}
    video_data = story.get("video_data") if isinstance(story, dict) else None
    if isinstance(video_data, dict) and (video_data.get("video_id") or video_data.get("id")):
        videos.append(video_data)

    asset_feed = creative.get("asset_feed_spec") or {}
    asset_videos = asset_feed.get("videos") if isinstance(asset_feed, dict) else None
    if isinstance(asset_videos, list):
        videos.extend(item for item in asset_videos if isinstance(item, dict))
    return videos


def _creative_video_asset(creative):
    videos = _creative_video_assets(creative)
    return videos[0] if videos else {}


def _creative_video_id(creative):
    video = _creative_video_asset(creative)
    return video.get("video_id") or video.get("id") or ""


def _creative_video_thumbnail_url(creative):
    video = _creative_video_asset(creative)
    return (
        video.get("thumbnail_url")
        or video.get("image_url")
        or video.get("picture")
        or ""
    )


def _is_technical_meta_name(value):
    raw = str(value or "").strip()
    return "{{" in raw or "}}" in raw


def _meta_ad_display_name(row, creative):
    ad_name = str((row or {}).get("name") or "").strip()
    if ad_name and not _is_technical_meta_name(ad_name):
        return ad_name
    creative_name = str((creative or {}).get("name") or "").strip()
    if creative_name and not _is_technical_meta_name(creative_name):
        return creative_name
    return _creative_text(creative, "title") or "Anuncio activo"


def _creative_text(creative, *keys):
    if not isinstance(creative, dict):
        return ""
    for key in keys:
        value = creative.get(key)
        if value:
            return str(value)
    story = creative.get("object_story_spec") or {}
    for section in ("link_data", "video_data", "photo_data"):
        block = story.get(section) if isinstance(story, dict) else None
        if not isinstance(block, dict):
            continue
        for key in keys:
            value = block.get(key)
            if value:
                return str(value)
    asset_feed = creative.get("asset_feed_spec") or {}
    for key in keys:
        plural_key = {"body": "bodies"}.get(key, f"{key}s")
        items = asset_feed.get(plural_key) if isinstance(asset_feed, dict) else None
        if isinstance(items, list) and items:
            value = (items[0] or {}).get("text") or (items[0] or {}).get(key)
            if value:
                return str(value)
    return ""


def _meta_preview_formats(row, has_video):
    normalized_name = normalize_text((row or {}).get("name"))
    if has_video and "reel" in normalized_name:
        return ("INSTAGRAM_REELS", "INSTAGRAM_STANDARD", "MOBILE_FEED_STANDARD")
    if has_video:
        return ("INSTAGRAM_STANDARD", "MOBILE_FEED_STANDARD", "DESKTOP_FEED_STANDARD")
    return ()


def _meta_row_is_comfama(row):
    creative = (row or {}).get("creative") or {}
    campaign = (row or {}).get("campaign") or {}
    adset = (row or {}).get("adset") or {}
    values = [
        (row or {}).get("name"),
        campaign.get("name"),
        adset.get("name"),
        creative.get("name"),
    ]
    return any("comfama" in normalize_text(value) for value in values)


def _meta_ad_preview_url(client, row, has_video, force_preview=False):
    ad_id = (row or {}).get("id")
    if not ad_id or not (has_video or force_preview):
        return ""
    formats = _meta_preview_formats(row, has_video) or ("INSTAGRAM_STANDARD", "MOBILE_FEED_STANDARD")
    for ad_format in formats:
        try:
            preview_url = client.get_ad_preview_iframe_src(ad_id, ad_format=ad_format)
        except Exception:
            continue
        if preview_url:
            return preview_url
    return ""


def _meta_insight_payload(row):
    insights = row.get("insights") if isinstance(row, dict) else {}
    data = insights.get("data") if isinstance(insights, dict) else None
    if isinstance(data, list) and data:
        return data[0] or {}
    return {}


def _meta_action_value(items, action_types):
    wanted = {normalize_text(item) for item in action_types}
    total = ZERO
    for item in items or []:
        if normalize_text((item or {}).get("action_type")) in wanted:
            total += parse_decimal((item or {}).get("value"))
    return total


def _meta_first_value(items, action_types):
    wanted = {normalize_text(item) for item in action_types}
    for item in items or []:
        if normalize_text((item or {}).get("action_type")) in wanted:
            return parse_decimal((item or {}).get("value"))
    return ZERO


def _meta_preferred_value(items, action_types):
    rows = items or []
    for action_type in action_types:
        wanted = normalize_text(action_type)
        for item in rows:
            if normalize_text((item or {}).get("action_type")) == wanted:
                return parse_decimal((item or {}).get("value"))
    return ZERO


def _meta_parse_created_at(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _meta_ad_maturity(created_time, reference_date):
    created_date = _meta_parse_created_at(created_time)
    if not created_date:
        return {
            "level": "unknown",
            "label": "Sin dato",
            "age_days": None,
            "description": "Meta no devolvio fecha de activacion para este anuncio.",
        }
    age_days = max(0, (reference_date - created_date).days)
    if age_days < 14:
        return {
            "level": "low",
            "label": "Bajo",
            "age_days": age_days,
            "description": "Activado hace poco; leer ventas y ROAS como senales tempranas.",
        }
    if age_days < 45:
        return {
            "level": "medium",
            "label": "Medio",
            "age_days": age_days,
            "description": "Ya tiene aprendizaje inicial, pero aun puede estabilizar rendimiento.",
        }
    return {
        "level": "high",
        "label": "Alto",
        "age_days": age_days,
        "description": "Lleva varias semanas activo; comparar eficiencia contra anuncios nuevos.",
    }


def _meta_ad_metrics(row):
    insight = _meta_insight_payload(row)
    actions = insight.get("actions") or []
    action_values = insight.get("action_values") or []
    cost_per_action = insight.get("cost_per_action_type") or []
    purchase_types = (
        "offsite_conversion.fb_pixel_purchase",
        "onsite_web_purchase",
        "website_purchase",
        "purchase",
        "omni_purchase",
    )
    spend = parse_decimal(insight.get("spend"))
    impressions = parse_quantity(insight.get("impressions"))
    reach = parse_quantity(insight.get("reach"))
    clicks = parse_quantity(insight.get("clicks"))
    link_clicks = int(_meta_action_value(actions, ("link_click", "inline_link_click")) or parse_decimal(insight.get("inline_link_clicks")) or 0)
    purchases = int(_meta_preferred_value(actions, purchase_types) or 0)
    purchase_value = _meta_preferred_value(action_values, purchase_types)
    cpa_purchase = _meta_preferred_value(cost_per_action, purchase_types) or _safe_ratio(spend, Decimal(purchases))
    roas_values = insight.get("purchase_roas") or insight.get("website_purchase_roas") or []
    roas = _meta_preferred_value(roas_values, purchase_types + ("website_purchase_roas",))
    if not roas:
        roas = _safe_ratio(purchase_value, spend)
    if not purchase_value and roas and spend:
        purchase_value = roas * spend
    ctr = parse_decimal(insight.get("ctr"))
    if not ctr:
        ctr = _safe_ratio(Decimal(clicks) * Decimal("100"), Decimal(impressions))
    cpc = parse_decimal(insight.get("cpc")) or _safe_ratio(spend, Decimal(clicks))
    cpm = parse_decimal(insight.get("cpm")) or _safe_ratio(spend * Decimal("1000"), Decimal(impressions))
    frequency = _safe_ratio(Decimal(impressions), Decimal(reach))

    return {
        "spend": float(spend),
        "impressions": impressions,
        "reach": reach,
        "clicks": clicks,
        "link_clicks": link_clicks,
        "ctr": round(float(ctr), 2) if ctr else 0,
        "cpc": round(float(cpc), 2) if cpc else 0,
        "cpm": round(float(cpm), 2) if cpm else 0,
        "frequency": round(float(frequency), 2) if frequency else 0,
        "purchases": purchases,
        "purchase_value": float(purchase_value),
        "cpa_purchase": round(float(cpa_purchase), 2) if cpa_purchase else 0,
        "roas": round(float(roas), 2) if roas else 0,
    }


def _build_meta_ads_pacing_insights(ads):
    if not ads:
        return {"positive": [], "negative": []}

    def metric(ad, key):
        return parse_decimal((ad.get("metrics") or {}).get(key))

    def ad_label(ad):
        return ad.get("title") or ad.get("name") or "Anuncio activo"

    spend_ads = [ad for ad in ads if metric(ad, "spend") > 0]
    purchase_ads = [ad for ad in spend_ads if metric(ad, "purchases") > 0]
    positive = []
    negative = []
    used_positive = set()
    used_negative = set()

    def add_positive(ad, title, message):
        ad_id = ad.get("id") or ad_label(ad)
        if ad_id in used_positive or len(positive) >= 3:
            return
        used_positive.add(ad_id)
        positive.append({"title": title, "message": message})

    def add_negative(ad, title, message, recommendation):
        ad_id = ad.get("id") or ad_label(ad)
        if ad_id in used_negative or len(negative) >= 3:
            return
        used_negative.add(ad_id)
        negative.append({"title": title, "message": message, "recommendation": recommendation})

    top_purchases = sorted(purchase_ads, key=lambda ad: (metric(ad, "purchases"), metric(ad, "roas"), metric(ad, "spend")), reverse=True)
    if top_purchases:
        ad = top_purchases[0]
        add_positive(
            ad,
            "Mayor volumen de compras",
            f"{ad_label(ad)} registra {int(metric(ad, 'purchases'))} compras con ROAS {float(metric(ad, 'roas')):.2f}.",
        )

    top_roas = sorted(
        [ad for ad in purchase_ads if metric(ad, "roas") > 0],
        key=lambda ad: (metric(ad, "roas"), metric(ad, "purchases"), metric(ad, "spend")),
        reverse=True,
    )
    if top_roas:
        ad = top_roas[0]
        add_positive(
            ad,
            "Mejor eficiencia",
            f"{ad_label(ad)} lidera en ROAS con {float(metric(ad, 'roas')):.2f} sobre {format_cop(metric(ad, 'spend'))} de inversion.",
        )

    efficient_cpa = sorted(
        [ad for ad in purchase_ads if metric(ad, "cpa_purchase") > 0],
        key=lambda ad: (metric(ad, "cpa_purchase"), -metric(ad, "purchases")),
    )
    if efficient_cpa:
        ad = efficient_cpa[0]
        add_positive(
            ad,
            "CPA mas sano",
            f"{ad_label(ad)} compra a {format_cop(metric(ad, 'cpa_purchase'))} con {int(metric(ad, 'purchases'))} compras en el periodo.",
        )

    no_purchase_spend = sorted(
        [ad for ad in spend_ads if metric(ad, "purchases") == 0],
        key=lambda ad: metric(ad, "spend"),
        reverse=True,
    )
    if no_purchase_spend:
        ad = no_purchase_spend[0]
        add_negative(
            ad,
            "Gasto sin compras",
            f"{ad_label(ad)} invierte {format_cop(metric(ad, 'spend'))} sin compras registradas en el rango.",
            "Revisar segmentacion, destino y creativo antes de seguir aumentando presupuesto.",
        )

    low_roas = sorted(
        [ad for ad in purchase_ads if metric(ad, "roas") and metric(ad, "roas") < Decimal("1.5")],
        key=lambda ad: (metric(ad, "roas"), -metric(ad, "spend")),
    )
    if low_roas:
        ad = low_roas[0]
        add_negative(
            ad,
            "ROAS por debajo del punto sano",
            f"{ad_label(ad)} tiene ROAS {float(metric(ad, 'roas')):.2f} con {int(metric(ad, 'purchases'))} compras.",
            "Mantenerlo en observacion y mover presupuesto hacia piezas con ROAS y compras consistentes.",
        )

    high_cpc = sorted(
        [ad for ad in spend_ads if metric(ad, "cpc") > 0 and metric(ad, "clicks") >= 20],
        key=lambda ad: metric(ad, "cpc"),
        reverse=True,
    )
    if high_cpc:
        ad = high_cpc[0]
        add_negative(
            ad,
            "Trafico costoso",
            f"{ad_label(ad)} tiene CPC de {format_cop(metric(ad, 'cpc'))} y CTR {float(metric(ad, 'ctr')):.2f}%.",
            "Probar otro gancho visual o primer texto para bajar friccion antes del clic.",
        )

    if not positive and spend_ads:
        top_spend = max(spend_ads, key=lambda ad: metric(ad, "spend"))
        positive.append(
            {
                "title": "Lectura en progreso",
                "message": f"Hay {len(spend_ads)} anuncios activos con inversion; aun no aparece un ganador claro por compras o ROAS.",
            }
        )
        if not negative:
            add_negative(
                top_spend,
                "Sin ganador claro",
                f"{ad_label(top_spend)} concentra {format_cop(metric(top_spend, 'spend'))} de inversion.",
                "Esperar mas conversiones o redistribuir hacia creatividades con senales tempranas de compra.",
            )

    return {"positive": positive[:3], "negative": negative[:3]}


def build_uva_meta_ads_preview(filters, limit=None, comfama_scope="exclude", force_refresh=False, timeout=None, allow_live_fetch=True):
    """Construye el panel de anuncios activos de Meta.

    `force_refresh` y `timeout` existen para el precalentamiento en segundo
    plano (ver el comando warm_meta_ads_preview): alli conviene ignorar la
    cache y esperar a Meta lo que haga falta, porque nadie esta mirando.

    `allow_live_fetch=False` es lo que usan las vistas. La llamada a Meta son
    varias peticiones HTTP encadenadas y medi 16 s en /uva/ con la cache fria,
    con el usuario esperando la pagina completa. Sin permiso para ir a Meta, la
    funcion devuelve lo que haya en cache o un estado `pending`, y el panel se
    completa despues con una peticion aparte.
    """
    requested_country = (filters.get("country") or "").upper()
    country_code = requested_country or "CO"

    country = Country.objects.filter(code__iexact=country_code).first()
    country_label = country.name if country else country_code
    account_id = getattr(settings, f"META_{country_code}_ACCOUNT_ID", "")
    token = getattr(settings, "META_ACCESS_TOKEN", "")
    if not account_id or not token:
        return {
            "ads": [],
            "pacing_insights": {"positive": [], "negative": []},
            "country_code": country_code,
            "country_label": country_label,
            "requires_country": False,
            "message": f"No hay credenciales Meta configuradas para {country_label}.",
        }

    date_start = _parse_filter_date(filters.get("date_start")) or timezone.localdate()
    date_end = _parse_filter_date(filters.get("date_end")) or date_start
    cache_key = "uva-meta-ads-preview:{country}:{start}:{end}:{limit}:{scope}".format(
        country=country_code,
        start=date_start.isoformat(),
        end=date_end.isoformat(),
        limit=limit or "default",
        scope=comfama_scope,
    )
    if not force_refresh:
        cached_preview = cache.get(cache_key)
        if cached_preview is not None:
            return cached_preview

    if not allow_live_fetch:
        return {
            "ads": [],
            "pacing_insights": {"positive": [], "negative": []},
            "country_code": country_code,
            "country_label": country_label,
            "requires_country": False,
            "pending": True,
            "message": f"Preparando los anuncios activos de {country_label}. El panel se completa en unos segundos.",
        }

    fallback_ttl = _setting_int("META_ADS_PREVIEW_FALLBACK_CACHE_SECONDS", 120)

    client = MetaAdsClient(
        token,
        api_version=getattr(settings, "META_API_VERSION", "v20.0"),
        timeout=int(timeout) if timeout else _setting_int("META_ADS_PREVIEW_TIMEOUT", 8),
    )
    max_records = _setting_int("META_ADS_PREVIEW_MAX_RECORDS", 36)
    try:
        rows = client.get_active_ads(
            account_id,
            limit=limit,
            date_start=date_start,
            date_end=date_end,
            max_records=max_records,
        )
    except Exception:
        logger.exception("Meta Ads preview fallo para %s (%s a %s)", country_code, date_start, date_end)
        failure = {
            "ads": [],
            "pacing_insights": {"positive": [], "negative": []},
            "country_code": country_code,
            "country_label": country_label,
            "requires_country": False,
            "message": f"No fue posible cargar anuncios activos de Meta para {country_label}. Intenta actualizar de nuevo en unos minutos.",
        }
        # Cachear el fallo evita repetir el camino lento en cada request, pero
        # un precalentamiento fallido no debe borrar un panel bueno ya guardado.
        if force_refresh and cache.get(cache_key) is not None:
            logger.warning("Se conserva el preview de Meta en cache para %s tras un precalentamiento fallido", country_code)
        else:
            cache.set(cache_key, failure, fallback_ttl)
        return failure

    image_hashes = []
    for row in rows:
        image_hashes.extend(_creative_image_hashes(row.get("creative") or {}))
    try:
        image_lookup = client.get_ad_images_by_hashes(account_id, image_hashes)
    except Exception:
        logger.warning("No se pudieron resolver imagenes de Meta para %s", country_code, exc_info=True)
        image_lookup = {}

    ads = []
    max_preview_fetches = _setting_int("META_ADS_PREVIEW_MAX_IFRAMES", 8)
    for row in rows:
        is_comfama = _meta_row_is_comfama(row)
        if comfama_scope == "exclude" and is_comfama:
            continue
        if comfama_scope == "only" and not is_comfama:
            continue

        creative = row.get("creative") or {}
        campaign = row.get("campaign") or {}
        adset = row.get("adset") or {}
        video_id = _creative_video_id(creative)
        display_name = _meta_ad_display_name(row, creative)
        normalized_ad_text = " ".join(
            normalize_text(value)
            for value in (
                row.get("name"),
                display_name,
                creative.get("name"),
                campaign.get("name"),
                adset.get("name"),
            )
            if value
        )
        looks_like_video = any(marker in normalized_ad_text for marker in ("reel", "video", "story"))
        has_video = bool(video_id or looks_like_video)
        headline = _creative_text(creative, "title")
        destination_url = (
            creative.get("link_url")
            or creative.get("object_url")
            or _nested_lookup(creative, "object_story_spec", "link_data", "link")
        )
        maturity = _meta_ad_maturity(row.get("created_time") or "", date_end)
        ads.append(
            {
                "id": row.get("id", ""),
                "name": display_name,
                "raw_name": row.get("name") or creative.get("name") or "",
                "created_time": row.get("created_time") or "",
                "updated_time": row.get("updated_time") or "",
                "maturity": maturity,
                "maturity_level": maturity["level"],
                "maturity_label": maturity["label"],
                "maturity_description": maturity["description"],
                "maturity_age_days": maturity["age_days"],
                "campaign_name": campaign.get("name") or "",
                "adset_name": adset.get("name") or "",
                "status": row.get("effective_status") or row.get("status") or "ACTIVE",
                "image_url": _creative_video_thumbnail_url(creative) or _creative_image_url(creative, image_lookup=image_lookup),
                "media_kind": "video" if has_video else "image",
                "video_id": video_id,
                "preview_url": _meta_ad_preview_url(
                    client,
                    row,
                    has_video,
                    force_preview=looks_like_video or (is_comfama and not has_video),
                )
                if len(ads) < max_preview_fetches
                else "",
                "title": display_name,
                "headline": headline,
                "body": _creative_text(creative, "body", "message"),
                "cta": creative.get("call_to_action_type") or "",
                "destination_url": destination_url,
                "metrics": _meta_ad_metrics(row),
            }
        )
        if limit and len(ads) >= int(limit):
            break

    ads.sort(key=lambda item: item.get("created_time") or "", reverse=True)

    # Meta devuelve HTTP 500 "Please reduce the amount of data" de forma
    # intermitente sobre la peticion que trae los insights. Cuando pasa, el cliente
    # termina resolviendo sin ellos y todos los anuncios quedan con inversion, ROAS
    # y compras en cero: el panel se ve normal pero no dice nada, y ordenar por
    # "mas compras" no cambia nada porque todo vale cero. Hay que decirlo.
    metrics_unavailable = bool(rows) and not any(_meta_insight_payload(row) for row in rows)
    preview = {
        "ads": ads,
        "pacing_insights": _build_meta_ads_pacing_insights(ads),
        "country_code": country_code,
        "country_label": country_label,
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "requires_country": False,
        "metrics_unavailable": metrics_unavailable,
        "message": "" if ads else f"No se encontraron anuncios activos en la cuenta Meta de {country_label}.",
    }
    # Un resultado vacio tambien se cachea (con TTL corto): antes cada request
    # sin anuncios repetia la ronda completa de llamadas a Meta.
    ttl = _setting_int("META_ADS_PREVIEW_CACHE_SECONDS", 900) if ads else fallback_ttl
    cache.set(cache_key, preview, ttl)
    return preview
