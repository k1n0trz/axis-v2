from django import template
from django.utils.safestring import mark_safe

from reports.sanitizers import sanitize_rich_text

register = template.Library()

ROAS_SETTING_CACHE_KEY = "roas-traffic-light-setting"
ROAS_SETTING_CACHE_SECONDS = 60


def _roas_cache():
    from django.core.cache import caches

    # En memoria del proceso: este filtro se invoca una vez por cada tarjeta de
    # KPI, asi que una cache respaldada por base de datos no ahorraria nada.
    try:
        return caches["local"]
    except Exception:
        return caches["default"]


def _roas_setting():
    from reports.models import RoasTrafficLightSetting

    cache = _roas_cache()
    setting = cache.get(ROAS_SETTING_CACHE_KEY)
    if setting is None:
        setting = RoasTrafficLightSetting.get_active()
        cache.set(ROAS_SETTING_CACHE_KEY, setting, ROAS_SETTING_CACHE_SECONDS)
    return setting


@register.filter
def sanitize_html(value):
    """Renderiza HTML de usuario dejando solo formato basico y enlaces seguros."""
    return mark_safe(sanitize_rich_text(value))


@register.filter
def get_item(mapping, key):
    return mapping.get(key, 0) if mapping else 0


@register.filter
def task_status_class(status):
    return {
        "completed": "success",
        "in_progress": "primary",
        "pending": "secondary",
        "blocked": "danger",
    }.get(status, "secondary")


@register.filter
def task_priority_class(priority):
    return {
        "critical": "danger",
        "high": "warning text-dark",
        "medium": "info text-dark",
        "low": "secondary",
    }.get(priority, "secondary")


@register.filter
def cop(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "$0 COP"
    formatted = f"{number:,.0f}".replace(",", ".")
    return f"${formatted} COP"


@register.filter
def signed_percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0,0%"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%".replace(".", ",")


@register.filter
def roi_percent(value):
    try:
        number = float(value or 0) * 100
    except (TypeError, ValueError):
        return "0,0%"
    return f"{number:.1f}%".replace(".", ",")


@register.filter
def percent_value(value):
    try:
        number = float(value or 0) * 100
    except (TypeError, ValueError):
        return "0,0%"
    return f"{number:.1f}%".replace(".", ",")


# Marcas cuyo ROAS no se semaforiza. DistriSex es mayorista y su venta no la
# mueve la pauta: 292.552 COP de inversion contra 439 M COP de venta en 6 dias dan
# un ROAS de ~1.500x. Pintarlo verde no informa nada y, peor, sugiere que la pauta
# esta funcionando cuando no es lo que sostiene el negocio.
UNIDADES_SIN_SEMAFORO_ROAS = {"distrisex"}


def _roas_color(value, business_unit=""):
    if str(business_unit or "").strip().lower() in UNIDADES_SIN_SEMAFORO_ROAS:
        return "neutral"
    try:
        return _roas_setting().color_for(value)
    except Exception:
        return "red"


@register.filter
def roas_signal_class(value, business_unit=""):
    return f"roas-signal roas-signal-{_roas_color(value, business_unit)}"


@register.filter
def roas_signal_label(value):
    return ""


@register.filter
def roas_value_class(value, business_unit=""):
    return f"roas-value roas-value-{_roas_color(value, business_unit)}"
