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
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from openpyxl.utils.datetime import from_excel

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


def parse_excel_date(value):
    """Fecha desde una celda de Excel, un ISO, un serial o un datetime."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return from_excel(value).date()
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_filter_date(value):
    """Fecha de un filtro de la interfaz. Vacio es None, no un error."""
    return parse_excel_date(value) if value else None
