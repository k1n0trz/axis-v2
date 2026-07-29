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


@register.filter
def roas_signal_class(value):
    try:
        color = _roas_setting().color_for(value)
    except Exception:
        color = "red"
    return f"roas-signal roas-signal-{color}"


@register.filter
def roas_signal_label(value):
    return ""


@register.filter
def roas_value_class(value):
    try:
        color = _roas_setting().color_for(value)
    except Exception:
        color = "red"
    return f"roas-value roas-value-{color}"
