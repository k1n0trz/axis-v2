"""Lectura de numeros que vienen de hojas de calculo.

Existia una copia de `parse_decimal` en cinco archivos, todas con el mismo
cuerpo: `str(value).replace(",", "")` y luego `Decimal(...)`. Eso convertia
silenciosamente "16,72" en 1672 (cien veces mas), "1.234,56" en 1,23456 y
"$ 16,72" en 0, perdiendo la linea completa. Nadie lo notaba porque el resultado
es un numero perfectamente valido, solo equivocado.

Las hojas de despachos las llenan personas con Excel en es-CO, asi que la coma
como separador decimal aparece en cuanto una celda queda como texto, y que haya
texto en columnas numericas ya esta comprobado: en el archivo real hay una fila
con CANTIDAD="B".

## Reglas

Si el valor ya es numerico (int, float, Decimal) se usa tal cual: openpyxl
devuelve numeros para las celdas numericas y ahi no hay nada que interpretar.

Sobre texto se quitan primero los simbolos de moneda y los espacios, para que
"$ 16,72" o "USD 16.72" no se pierdan. **Si lo que queda tiene una letra, no es un
importe**: la hoja de despachos tiene una columna SKU con codigos como
"UV-BCO-7009-A", y sin esa regla entraba como -7009, que en COP son 26 millones
negativos. Un guion interno tambien descalifica: "002-B" no es 2. Despues:

- Con coma y punto, el separador decimal es **el ultimo de los dos**:
  "1.234,56" -> 1234.56 y "1,234.56" -> 1234.56.
- Con un solo tipo de separador repetido, es de miles: "1.234.567" -> 1234567.
- Con un solo separador y **exactamente tres digitos** detras, es de miles:
  "1.234" -> 1234 y "1,234" -> 1234.
- Con un solo separador y cualquier otra cantidad de digitos, es decimal:
  "16,72" -> 16.72 y "16.72" -> 16.72.

El caso de tres digitos es genuinamente ambiguo: "1,234" puede ser mil doscientos
treinta y cuatro o uno con 234 milesimas. Se resuelve como miles porque en estas
hojas los importes en COP son enteros grandes y los precios en USD no llevan tres
decimales. `google_ads_import.parse_decimal` ya habia llegado a la misma
conclusion sobre su workbook, con una heuristica propia que se conserva alli.

Lo ilegible devuelve el valor por defecto, no una excepcion: una fila rara no
debe tumbar la importacion del dia.
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")

# Simbolos de moneda y codigos que pueden acompañar a un importe. Se quitan antes
# de decidir si lo que queda es un numero.
_CURRENCY = re.compile(r"(?i)\b(usd|cop|mxn|eur|ars|clp|pen)\b|[$€£¥]")
# Cualquier letra. Si sobrevive a la limpieza de moneda, el valor no es un importe.
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
# Todo lo que no sea digito, coma, punto o signo menos.
_NOISE = re.compile(r"[^\d,.\-]")


def parse_decimal(value, default=ZERO):
    """Convierte a Decimal un valor de hoja de calculo. Ver reglas arriba."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        # True valdria 1 y ninguna columna de importe quiere eso.
        return default
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    raw = str(value if value is not None else "").strip()
    if not raw:
        return default

    # Moneda y espacios fuera; si lo que queda trae una letra, no es un importe.
    without_currency = _CURRENCY.sub("", raw)
    without_currency = "".join(without_currency.split())
    if _LETTER.search(without_currency):
        return default

    cleaned = _NOISE.sub("", without_currency)
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-")
    # Un guion interno pertenece a un codigo, no a un importe: "002-B" no es 2.
    if "-" in cleaned:
        return default
    if not cleaned or not any(char.isdigit() for char in cleaned):
        return default

    normalized = _normalize_separators(cleaned)
    try:
        number = Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError):
        return default
    return -number if negative else number


def _normalize_separators(cleaned):
    has_comma = "," in cleaned
    has_dot = "." in cleaned

    if has_comma and has_dot:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        return cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")

    if not has_comma and not has_dot:
        return cleaned

    sep = "," if has_comma else "."
    if cleaned.count(sep) > 1:
        return cleaned.replace(sep, "")

    whole, _, decimals = cleaned.partition(sep)
    if len(decimals) == 3:
        return whole + decimals
    return f"{whole}.{decimals}" if decimals else whole


def parse_quantity(value):
    """Cantidad de unidades. Lo ilegible o negativo cuenta como cero."""
    number = parse_decimal(value)
    return int(number) if number > 0 else 0


def normalize_header(value):
    """Cabecera de columna comparable: sin acentos, sin espacios sobrantes."""
    raw_text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return "".join(char for char in raw_text if not unicodedata.combining(char))
