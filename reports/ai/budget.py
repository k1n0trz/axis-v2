"""Techo de gasto de la IA, por usuario y por dia.

Va desde el primer commit y no despues. Un widget de chat visible en todas las
paginas puede convertirse en muchas llamadas sin que nadie lo note, y el costo no
avisa hasta que llega la factura. El mismo razonamiento que llevo a que el panel de
Meta no bloquee el render: lo que no se ve, no se controla.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

MTOK = Decimal("1000000")


def _setting_decimal(name, default):
    try:
        return Decimal(str(getattr(settings, name, default)))
    except Exception:
        return Decimal(str(default))


def cost_for(prompt_tokens, completion_tokens):
    """Costo estimado en USD. Los precios son settings porque cambian."""
    entrada = _setting_decimal("AI_INPUT_COST_PER_MTOK", "0.27") * Decimal(prompt_tokens or 0) / MTOK
    salida = _setting_decimal("AI_OUTPUT_COST_PER_MTOK", "1.10") * Decimal(completion_tokens or 0) / MTOK
    return (entrada + salida).quantize(Decimal("0.000001"))


def usage_today(user):
    """Tokens y costo que este usuario ya gasto hoy."""
    from reports.models import AiMessage

    inicio = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    fila = AiMessage.objects.filter(conversation__user=user, created_at__gte=inicio).aggregate(
        prompt=Sum("prompt_tokens"),
        completion=Sum("completion_tokens"),
        cost=Sum("cost_usd"),
    )
    return {
        "tokens": (fila["prompt"] or 0) + (fila["completion"] or 0),
        "cost_usd": fila["cost"] or Decimal("0"),
    }


class BudgetExceeded(RuntimeError):
    """El usuario agoto su cupo del dia. No es un error de la IA: es un limite."""


def check_budget(user):
    """Lanza BudgetExceeded si el usuario ya no tiene cupo hoy."""
    limite_tokens = int(getattr(settings, "AI_DAILY_TOKEN_BUDGET", 400000) or 0)
    limite_costo = _setting_decimal("AI_DAILY_COST_LIMIT_USD", "2.00")
    gastado = usage_today(user)

    if limite_tokens and gastado["tokens"] >= limite_tokens:
        raise BudgetExceeded(
            f"Alcanzaste el limite de {limite_tokens:,} tokens de hoy "
            f"({gastado['tokens']:,} usados). Se reinicia manana."
        )
    if limite_costo > 0 and gastado["cost_usd"] >= limite_costo:
        raise BudgetExceeded(
            f"Alcanzaste el limite de {limite_costo} USD de hoy "
            f"({gastado['cost_usd']} usados). Se reinicia manana."
        )
    return gastado


def usage_report(user):
    """Gasto de la IA: el propio siempre, y el del equipo si la persona lo lidera.

    Un analista no necesita ver cuanto gasta el resto; un jefe si, porque el tope es por
    persona y el que se dispara no avisa solo.
    """
    from django.contrib.auth.models import User

    from reports.models import AiMessage

    ahora = timezone.localtime()
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

    def _rango(desde):
        fila = AiMessage.objects.filter(created_at__gte=desde).aggregate(
            prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"), cost=Sum("cost_usd")
        )
        return fila

    def _mio(desde):
        fila = AiMessage.objects.filter(conversation__user=user, created_at__gte=desde).aggregate(
            prompt=Sum("prompt_tokens"), completion=Sum("completion_tokens"), cost=Sum("cost_usd")
        )
        return {
            "tokens": (fila["prompt"] or 0) + (fila["completion"] or 0),
            "cost_usd": float(fila["cost"] or 0),
        }

    perfil = getattr(user, "profile", None)
    rol = getattr(perfil, "role", None)
    lidera = bool(getattr(rol, "is_leadership_role", False)) or user.is_superuser

    reporte = {
        "mio": {
            "hoy": _mio(hoy),
            "ultimos_7": _mio(hoy - timedelta(days=6)),
            "ultimos_30": _mio(hoy - timedelta(days=29)),
        },
        "topes": {
            "tokens_por_dia": int(getattr(settings, "AI_DAILY_TOKEN_BUDGET", 0) or 0),
            "usd_por_dia": float(_setting_decimal("AI_DAILY_COST_LIMIT_USD", "2.00")),
        },
        "precios_por_mtok": {
            "entrada": float(_setting_decimal("AI_INPUT_COST_PER_MTOK", "0.27")),
            "salida": float(_setting_decimal("AI_OUTPUT_COST_PER_MTOK", "1.10")),
        },
        "lidera": lidera,
    }

    if lidera:
        equipo = _rango(hoy - timedelta(days=29))
        reporte["equipo"] = {
            "ultimos_30": {
                "tokens": (equipo["prompt"] or 0) + (equipo["completion"] or 0),
                "cost_usd": float(equipo["cost"] or 0),
            },
            "por_persona": [
                {
                    "usuario": fila["conversation__user__username"],
                    "tokens": (fila["prompt"] or 0) + (fila["completion"] or 0),
                    "cost_usd": float(fila["cost"] or 0),
                }
                for fila in AiMessage.objects.filter(created_at__gte=hoy - timedelta(days=29))
                .values("conversation__user__username")
                .annotate(
                    prompt=Sum("prompt_tokens"),
                    completion=Sum("completion_tokens"),
                    cost=Sum("cost_usd"),
                )
                .order_by("-cost")[:15]
            ],
        }
    return reporte
