"""Piezas que comparten los servicios de tablero.

Vivian dentro de `sales_dashboard`, que tenia 3.726 lineas y 112 funciones de
nivel superior. Sacarlas aparte es lo que permite mover a su propio modulo los
bloques cohesivos que las usan (Meta Ads, mapas, comparativas) sin crear un import
circular contra el modulo del que salen.

Los nombres pierden el guion bajo: aqui son la interfaz publica de un modulo
compartido, no ayudantes privados de otro. `sales_dashboard` los importa con alias
para no tocar sus cientos de llamadas existentes.
"""
import unicodedata
from decimal import Decimal

from django.conf import settings

ZERO = Decimal("0")


def setting_int(name, default):
    """Lee un entero de settings sin reventar si trae basura."""
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return int(default)


def safe_ratio(numerator, denominator):
    """Division que devuelve cero en vez de lanzar cuando el divisor es cero."""
    return (numerator / denominator) if denominator else ZERO


def normalize_text(value):
    """Texto comparable: sin acentos, sin espacios sobrantes, en minusculas."""
    raw = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip().lower()


def format_cop(value):
    """Formato de pesos colombianos, con punto de miles."""
    formatted = f"{float(value or 0):,.0f}".replace(",", ".")
    return f"${formatted} COP"
