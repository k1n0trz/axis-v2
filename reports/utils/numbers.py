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

Sobre texto, primero se descartan los caracteres que no son digito, separador ni
signo, para que "$ 16,72" o "USD 16.72" no se pierdan. Despues:

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

# Todo lo que no sea digito, coma, punto o signo menos.
_RUIDO = re.compile(r"[^\d,.\-]")


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

    limpio = _RUIDO.sub("", raw.replace(" ", " "))
    negativo = limpio.startswith("-")
    limpio = limpio.replace("-", "")
    if not limpio or not any(char.isdigit() for char in limpio):
        return default

    normalizado = _normalizar_separadores(limpio)
    try:
        numero = Decimal(normalizado)
    except (InvalidOperation, TypeError, ValueError):
        return default
    return -numero if negativo else numero


def _normalizar_separadores(limpio):
    tiene_coma = "," in limpio
    tiene_punto = "." in limpio

    if tiene_coma and tiene_punto:
        decimal_sep = "," if limpio.rfind(",") > limpio.rfind(".") else "."
        miles_sep = "." if decimal_sep == "," else ","
        return limpio.replace(miles_sep, "").replace(decimal_sep, ".")

    if not tiene_coma and not tiene_punto:
        return limpio

    sep = "," if tiene_coma else "."
    if limpio.count(sep) > 1:
        return limpio.replace(sep, "")

    entero, _, decimales = limpio.partition(sep)
    if len(decimales) == 3:
        return entero + decimales
    return f"{entero}.{decimales}" if decimales else entero


def parse_quantity(value):
    """Cantidad de unidades. Lo ilegible o negativo cuenta como cero."""
    numero = parse_decimal(value)
    return int(numero) if numero > 0 else 0


def normalize_header(value):
    """Cabecera de columna comparable: sin acentos, sin espacios sobrantes."""
    crudo = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return "".join(char for char in crudo if not unicodedata.combining(char))
