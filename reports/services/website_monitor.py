import re
import socket
import ssl
import time
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from django.utils import timezone

from reports.models import Website, WebsiteHealthCheck


REQUEST_TIMEOUT = 15
PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
SECURITY_HEADERS = [
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
]
SECURITY_HEADER_LABELS = {
    "strict-transport-security": "HSTS",
    "content-security-policy": "Politica de seguridad de contenido",
    "x-frame-options": "Proteccion contra iframes",
    "x-content-type-options": "Proteccion de tipo de contenido",
    "referrer-policy": "Politica de referencia",
    "permissions-policy": "Politica de permisos",
}


WEBSITE_SEED_ROWS = [
    {
        "name": "Copa Uva",
        "country_label": "Colombia",
        "url": "https://copauva.com/",
        "platform": Website.Platform.WORDPRESS,
        "stage": Website.Stage.ACTIVE,
        "display_order": 10,
    },
    {
        "name": "Copa Uva",
        "country_label": "Ecuador",
        "url": "https://copauva.com/ec/",
        "platform": Website.Platform.WORDPRESS,
        "stage": Website.Stage.ACTIVE,
        "display_order": 20,
    },
    {
        "name": "Copa Uva",
        "country_label": "Mexico",
        "url": "https://uvawomen.mx/",
        "platform": Website.Platform.WORDPRESS,
        "stage": Website.Stage.ACTIVE,
        "display_order": 30,
    },
    {
        "name": "Bali Sex Store",
        "country_label": "Colombia",
        "url": "https://balisexstore.com/",
        "platform": Website.Platform.SHOPIFY,
        "stage": Website.Stage.ACTIVE,
        "display_order": 40,
    },
]


def seed_websites():
    """Crea las webs que falten, sin tocar las que ya existen.

    Antes usaba `update_or_create`, asi que cada corrida reescribia url,
    plataforma, etapa, monitoreo y notas con los valores de este archivo: lo que
    el equipo editaba en el admin se perdia en la siguiente ejecucion. La semilla
    solo debe cubrir el arranque en frio; despues la fuente de verdad es la base.
    """
    _normalize_legacy_websites()
    websites = []
    for row in WEBSITE_SEED_ROWS:
        slug = _website_slug(row["name"], row.get("country_label", ""))
        website, _ = Website.objects.get_or_create(
            slug=slug,
            defaults={
                "name": row["name"],
                "country_label": row.get("country_label", ""),
                "url": row.get("url", ""),
                "platform": row.get("platform", Website.Platform.UNKNOWN),
                "stage": row.get("stage", Website.Stage.PENDING),
                "display_order": row.get("display_order", 0),
                "monitor_enabled": bool(row.get("url")),
                "notes": row.get("notes", ""),
            },
        )
        websites.append(website)
    return websites


def _normalize_legacy_websites():
    old_bali = Website.objects.filter(slug="bali-sex-store-mexico").first()
    new_bali_exists = Website.objects.filter(slug="bali-sex-store-colombia").exists()
    if old_bali and not new_bali_exists:
        old_bali.slug = "bali-sex-store-colombia"
        old_bali.country_label = "Colombia"
        old_bali.save(update_fields=["slug", "country_label", "updated_at"])


def scan_website(website):
    checked_at = timezone.now()
    payload = {
        "checked_at": checked_at.isoformat(),
        "url": website.url,
        "declared_platform": website.platform,
    }
    data = {
        "website": website,
        "checked_at": checked_at,
        "overall_status": WebsiteHealthCheck.OverallStatus.UNKNOWN,
        "availability_status": WebsiteHealthCheck.AvailabilityStatus.UNKNOWN,
        "final_url": "",
        "platform_detected": "",
        "security_headers_total": len(SECURITY_HEADERS),
        "missing_security_headers": SECURITY_HEADERS.copy(),
        "pagespeed_status": "unknown",
        "products_visible_status": "unknown",
        "raw_payload": payload,
    }

    if not website.url:
        data["overall_status"] = WebsiteHealthCheck.OverallStatus.UNKNOWN
        data["availability_status"] = WebsiteHealthCheck.AvailabilityStatus.UNKNOWN
        data["error_message"] = "URL pendiente."
        return WebsiteHealthCheck.objects.create(**data)

    parsed = urlparse(website.url)
    data["is_https"] = parsed.scheme == "https"
    if data["is_https"]:
        data.update(_ssl_status(parsed.hostname))

    try:
        started_at = time.perf_counter()
        response = requests.get(
            website.url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": "AxisWebsiteMonitor/1.0"},
        )
        data["response_time_ms"] = int((time.perf_counter() - started_at) * 1000)
        data["http_status"] = response.status_code
        data["final_url"] = response.url[:1000]
        data["availability_status"] = _availability_status(response)
        data["page_title"] = _extract_title(response.text)
        data["platform_detected"] = _detect_platform(response, website.platform)
        data.update(_security_headers(response.headers))
        pagespeed_payload = _pagespeed_metrics(response.url)
        # Lighthouse tarda y a veces se pasa del timeout. Cada corrida crea un
        # chequeo nuevo, asi que escribir nulos ahi borraba del tablero los
        # puntajes que ya se habian medido bien. Un fallo conserva el ultimo dato.
        if pagespeed_payload.get("pagespeed_status") != "ok":
            pagespeed_payload = _carry_over_pagespeed(website, pagespeed_payload)
        data.update(pagespeed_payload)
        # Sin esta llamada los contadores de producto quedaban siempre en
        # "unknown": la funcion existia pero nadie la invocaba.
        product_payload = _product_visibility(website, response.url)
        data.update(product_payload)
        payload["response_headers"] = dict(response.headers)
        payload["pagespeed_probe"] = pagespeed_payload.get("raw_pagespeed_probe", {})
        payload["product_probe"] = product_payload.get("raw_product_probe", {})
    except Exception as exc:
        data["overall_status"] = WebsiteHealthCheck.OverallStatus.CRITICAL
        data["availability_status"] = WebsiteHealthCheck.AvailabilityStatus.ERROR
        data["error_message"] = str(exc)
        return WebsiteHealthCheck.objects.create(**data)

    data["overall_status"] = _overall_status(data)
    data.pop("raw_pagespeed_probe", None)
    data.pop("raw_product_probe", None)
    return WebsiteHealthCheck.objects.create(**data)


def scan_active_websites():
    seed_websites()
    checks = []
    websites = Website.objects.filter(stage=Website.Stage.ACTIVE, monitor_enabled=True).order_by("display_order", "name")
    for website in websites:
        checks.append(scan_website(website))
    return checks


def latest_checks_by_website():
    checks = {}
    for check in WebsiteHealthCheck.objects.select_related("website").order_by("website_id", "-checked_at"):
        checks.setdefault(check.website_id, check)
    return checks


def _website_slug(name, country_label):
    raw = "-".join(part for part in [name, country_label] if part)
    return re.sub(r"[^a-z0-9-]+", "-", raw.lower().replace(" ", "-")).strip("-")


def _ssl_status(hostname):
    if not hostname:
        return {"ssl_valid": False}
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=REQUEST_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as wrapped:
                cert = wrapped.getpeercert()
        expires_raw = cert.get("notAfter")
        expires_at = datetime.strptime(expires_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt_timezone.utc)
        days_remaining = (expires_at - datetime.now(dt_timezone.utc)).days
        return {
            "ssl_valid": days_remaining >= 0,
            "ssl_expires_at": expires_at,
            "ssl_days_remaining": days_remaining,
        }
    except Exception:
        return {"ssl_valid": False}


def _availability_status(response):
    if response.history:
        return WebsiteHealthCheck.AvailabilityStatus.REDIRECT
    if 200 <= response.status_code < 400:
        return WebsiteHealthCheck.AvailabilityStatus.ONLINE
    if response.status_code >= 500:
        return WebsiteHealthCheck.AvailabilityStatus.OFFLINE
    return WebsiteHealthCheck.AvailabilityStatus.ERROR


def _extract_title(html):
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()[:255]


def _detect_platform(response, declared_platform):
    text = (response.text or "")[:100000].lower()
    headers = " ".join(f"{key}: {value}" for key, value in response.headers.items()).lower()
    if "cdn.shopify.com" in text or "x-shopify" in headers or "shopify" in headers:
        return Website.Platform.SHOPIFY
    if "wp-content" in text or "wp-json" in text or "wordpress" in text:
        return Website.Platform.WORDPRESS
    return declared_platform or Website.Platform.UNKNOWN


def _security_headers(headers):
    normalized = {key.lower(): value for key, value in headers.items()}
    missing = [header for header in SECURITY_HEADERS if header not in normalized]
    return {
        "security_headers_score": len(SECURITY_HEADERS) - len(missing),
        "security_headers_total": len(SECURITY_HEADERS),
        "missing_security_headers": [SECURITY_HEADER_LABELS.get(header, header) for header in missing],
    }


def _pagespeed_metrics(url):
    try:
        params = [
            ("url", url),
            ("strategy", "mobile"),
            ("category", "performance"),
            ("category", "accessibility"),
            ("category", "best-practices"),
            ("category", "seo"),
        ]
        api_key = getattr(settings, "PAGESPEED_API_KEY", "")
        if api_key:
            params.append(("key", api_key))
        response = requests.get(
            PAGESPEED_ENDPOINT,
            params=params,
            timeout=getattr(settings, "PAGESPEED_TIMEOUT", 90),
            headers={"User-Agent": "AxisWebsiteMonitor/1.0"},
        )
        if not response.ok:
            status = "quota_exceeded" if response.status_code == 429 else "error"
            return {
                "pagespeed_status": status,
                "raw_pagespeed_probe": {"status_code": response.status_code, "error": response.text[:500]},
            }
        payload = response.json()
        lighthouse = payload.get("lighthouseResult") or {}
        categories = lighthouse.get("categories") or {}
        audits = lighthouse.get("audits") or {}
        return {
            "pagespeed_status": "ok",
            "performance_score": _category_score(categories, "performance"),
            "accessibility_score": _category_score(categories, "accessibility"),
            "best_practices_score": _category_score(categories, "best-practices"),
            "seo_score": _category_score(categories, "seo"),
            "first_contentful_paint_ms": _audit_ms(audits, "first-contentful-paint"),
            "largest_contentful_paint_ms": _audit_ms(audits, "largest-contentful-paint"),
            "speed_index_ms": _audit_ms(audits, "speed-index"),
            "total_blocking_time_ms": _audit_ms(audits, "total-blocking-time"),
            "cumulative_layout_shift": _audit_numeric(audits, "cumulative-layout-shift"),
            "raw_pagespeed_probe": {
                "requested_url": url,
                "final_url": lighthouse.get("finalUrl", ""),
                "fetch_time": lighthouse.get("fetchTime", ""),
            },
        }
    except Exception as exc:
        return {
            "pagespeed_status": "error",
            "raw_pagespeed_probe": {"error": str(exc)},
        }


PAGESPEED_FIELDS = (
    "performance_score",
    "accessibility_score",
    "best_practices_score",
    "seo_score",
    "first_contentful_paint_ms",
    "largest_contentful_paint_ms",
    "speed_index_ms",
    "total_blocking_time_ms",
    "cumulative_layout_shift",
)


def _carry_over_pagespeed(website, failed_payload):
    """Reutiliza los ultimos puntajes buenos cuando Lighthouse falla."""
    previo = (
        WebsiteHealthCheck.objects.filter(website=website, pagespeed_status__in=("ok", "stale"))
        .exclude(performance_score=None)
        .order_by("-checked_at")
        .first()
    )
    if previo is None:
        return failed_payload

    heredado = {campo: getattr(previo, campo) for campo in PAGESPEED_FIELDS}
    heredado["pagespeed_status"] = "stale"
    probe = dict(failed_payload.get("raw_pagespeed_probe") or {})
    probe["carried_over_from"] = previo.checked_at.isoformat()
    heredado["raw_pagespeed_probe"] = probe
    return heredado


def _category_score(categories, key):
    score = (categories.get(key) or {}).get("score")
    if score is None:
        return None
    return int(round(float(score) * 100))


def _audit_ms(audits, key):
    numeric_value = (audits.get(key) or {}).get("numericValue")
    if numeric_value is None:
        return None
    return int(round(float(numeric_value)))


def _audit_numeric(audits, key):
    numeric_value = (audits.get(key) or {}).get("numericValue")
    if numeric_value is None:
        return None
    return Decimal(str(round(float(numeric_value), 3)))


def _product_visibility(website, final_url):
    platform = website.platform
    if platform == Website.Platform.SHOPIFY:
        return _shopify_products(website, final_url or website.url)
    if platform == Website.Platform.WORDPRESS:
        return _wordpress_products(website.url, final_url)
    return {"products_visible_status": "not_configured", "raw_product_probe": {}}


STORE_API_PATH = "wp-json/wc/store/v1/products?per_page=20"


def _wordpress_products(original_url, final_url):
    probe_urls = []
    for base in [original_url, final_url]:
        if not base:
            continue
        probe_urls.append(urljoin(base.rstrip("/") + "/", STORE_API_PATH))
        parsed = urlparse(base)
        # El origen solo sirve de respaldo cuando la web vive en la raiz. Para una
        # web en subcarpeta (copauva.com/ec/) el origen es otra tienda: Ecuador
        # terminaba reportando el catalogo de Colombia como si fuera propio.
        if parsed.path.strip("/"):
            continue
        probe_urls.append(urljoin(f"{parsed.scheme}://{parsed.netloc}/", STORE_API_PATH))

    return _probe_product_urls(dict.fromkeys(probe_urls), source="wordpress-store-api")


# Webs cuya tienda Shopify se puede leer con la Admin API. El escaparate publico
# de balisexstore.com responde 429 a /products.json de forma sostenida, asi que
# sin esto el contador de productos de Bali queda siempre vacio.
SHOPIFY_ADMIN_SITES = {
    "bali-sex-store-colombia": ("SHOPIFY_BALI_SHOP_DOMAIN", "SHOPIFY_BALI_ACCESS_TOKEN", "SHOPIFY_BALI_API_VERSION"),
}


def _shopify_products(website, base_url):
    admin_result = _shopify_admin_products(website)
    if admin_result is not None:
        return admin_result
    probe_url = urljoin(base_url.rstrip("/") + "/", "products.json?limit=20")
    return _probe_product_urls([probe_url], source="shopify-products-json")


def _shopify_admin_products(website):
    """Cuenta productos con la Admin API. Devuelve None si no aplica o falla."""
    config = SHOPIFY_ADMIN_SITES.get(website.slug)
    if not config:
        return None
    domain_setting, token_setting, version_setting = config
    domain = str(getattr(settings, domain_setting, "") or "").replace("https://", "").replace("http://", "").strip("/")
    token = getattr(settings, token_setting, "")
    if not domain or not token:
        return None

    version = getattr(settings, version_setting, "") or "2025-10"
    url = f"https://{domain}/admin/api/{version}/products.json"
    try:
        response = requests.get(
            url,
            # Solo lo que un visitante ve: la Admin API tambien devuelve
            # archivados y borradores, y contarlos infla el numero.
            params={"limit": 20, "status": "active", "published_status": "published", "fields": "id,title,variants"},
            headers={"X-Shopify-Access-Token": token, "User-Agent": "AxisWebsiteMonitor/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
        if not response.ok:
            return None
        products = response.json().get("products") or []
    except Exception:
        return None

    in_stock, out_of_stock = _stock_counts(products)
    return {
        "products_visible_status": "ok" if products else "empty",
        "products_visible_count": len(products),
        "products_in_stock_count": in_stock,
        "products_out_of_stock_count": out_of_stock,
        "raw_product_probe": {"source": "shopify-admin-api", "url": url},
    }


def _probe_product_urls(urls, source):
    last_error = ""
    for url in urls:
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "AxisWebsiteMonitor/1.0"})
            if not response.ok:
                last_error = f"{response.status_code} for {url}"
                continue
            payload = response.json()
            products = payload.get("products") if isinstance(payload, dict) else payload
            if not isinstance(products, list):
                last_error = f"Unexpected payload for {url}"
                continue
            in_stock, out_of_stock = _stock_counts(products)
            return {
                "products_visible_status": "ok" if products else "empty",
                "products_visible_count": len(products),
                "products_in_stock_count": in_stock,
                "products_out_of_stock_count": out_of_stock,
                "raw_product_probe": {"source": source, "url": url},
            }
        except Exception as exc:
            last_error = str(exc)
    return {
        "products_visible_status": "blocked",
        "raw_product_probe": {"source": source, "error": last_error},
    }


def _stock_counts(products):
    in_stock = 0
    out_of_stock = 0
    for product in products:
        if "is_in_stock" in product:
            if product.get("is_in_stock"):
                in_stock += 1
            else:
                out_of_stock += 1
            continue
        variants = product.get("variants") or []
        if variants:
            if any(int(variant.get("inventory_quantity") or 0) > 0 for variant in variants):
                in_stock += 1
            else:
                out_of_stock += 1
    return in_stock, out_of_stock


def _overall_status(data):
    http_status = data.get("http_status") or 0
    if data.get("availability_status") in {
        WebsiteHealthCheck.AvailabilityStatus.OFFLINE,
        WebsiteHealthCheck.AvailabilityStatus.ERROR,
    }:
        return WebsiteHealthCheck.OverallStatus.CRITICAL
    if http_status >= 500 or data.get("ssl_valid") is False:
        return WebsiteHealthCheck.OverallStatus.CRITICAL
    warning_conditions = [
        http_status >= 400,
        data.get("response_time_ms") and data["response_time_ms"] > 3000,
        data.get("ssl_days_remaining") is not None and data["ssl_days_remaining"] < 30,
        data.get("security_headers_score", 0) < 3,
        data.get("performance_score") is not None and data["performance_score"] < 50,
        data.get("accessibility_score") is not None and data["accessibility_score"] < 70,
    ]
    if any(warning_conditions):
        return WebsiteHealthCheck.OverallStatus.WARNING
    return WebsiteHealthCheck.OverallStatus.HEALTHY
