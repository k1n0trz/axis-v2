"""Detecta filas donde VALOR trae el total de la linea en vez del precio unitario.

La hoja de despachos tiene la convencion mezclada. VALOR es precio por unidad y el
importador lo multiplica por CANTIDAD, pero algunas filas ya traen el total
calculado, y multiplicarlas las duplica. En julio 2026 habia cuatro:

    07-03  Calzones M Moderado    cant 3   50.16  ->  16.72
    07-04  Calzones M Moderado    cant 2   34.02  ->  17.01
    07-07  Copa Uva talla A       cant 2   43.15  ->  21.57
    07-04  Calzones M Leve        cant 3   51.03  ->  17.01

Nadie las vio hasta que el total del mes no cuadro. El patron es reconocible: el
VALOR de la fila sospechosa es casi exactamente CANTIDAD veces el VALOR que el
mismo producto tiene en las demas filas.

Esto solo avisa. No corrige nada, porque la unica correccion valida es editar el
archivo fuente: si el importador "arreglara" la fila por su cuenta, el archivo y
Axis dirian cosas distintas y nadie sabria cual creer.
"""
from collections import defaultdict
from decimal import Decimal

# Cuanto puede alejarse el valor observado del esperado para seguir contando como
# la misma cifra. 2% cubre redondeos de centavos sin tragarse diferencias reales.
TOLERANCE = Decimal("0.02")


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


class UnitPriceAuditor:
    """Acumula filas y despues señala las que parecen traer el total de la linea.

    Uso:

        auditor = UnitPriceAuditor()
        for row in rows:
            auditor.record(product_name, quantity, unit_value, reference=sale_date)
        for warning in auditor.suspicious():
            ...
    """

    def __init__(self, tolerance=TOLERANCE):
        self.tolerance = Decimal(str(tolerance))
        self._rows = []
        self._by_product = defaultdict(list)

    def record(self, product_name, quantity, unit_value, reference="", in_range=True):
        """Registra una fila.

        `in_range=False` la usa solo para calibrar el precio del producto, sin
        reportarla. Sirve para alimentar el auditor con toda la hoja aunque la
        importacion cubra un solo dia: si el precio de referencia tuviera que
        estar en el mismo dia, casi nunca habria con que comparar.
        """
        name = " ".join(str(product_name or "").split()).lower()
        try:
            value = Decimal(str(unit_value))
        except Exception:
            return
        quantity = int(quantity or 0)
        if not name or value <= 0:
            return
        if in_range:
            self._rows.append((name, quantity, value, reference))
        # Solo las lineas de una unidad sirven de referencia: ahi VALOR es el
        # precio unitario sin ambiguedad posible.
        if quantity == 1:
            self._by_product[name].append(value)

    def _reference_unit_price(self, name):
        values = self._by_product.get(name)
        return _median(values) if values else None

    def suspicious(self):
        """Devuelve un aviso por fila que parece traer el total de la linea."""
        warnings = []
        for name, quantity, value, reference in self._rows:
            if quantity < 2:
                continue
            unit_price = self._reference_unit_price(name)
            if not unit_price:
                continue
            expected_as_total = unit_price * quantity
            if expected_as_total <= 0:
                continue
            deviation = abs(value - expected_as_total) / expected_as_total
            if deviation > self.tolerance:
                continue
            warnings.append(
                {
                    "product_name": name,
                    "quantity": quantity,
                    "sheet_value": value,
                    "reference_unit_price": unit_price,
                    "reference": reference,
                    "overcount": value * quantity - value,
                    "message": (
                        f"{reference} {name}: VALOR {value} con CANTIDAD {quantity} parece ser el total "
                        f"de la linea, no el precio unitario ({unit_price} en otras filas del mismo "
                        f"producto). Multiplicarlo la contaria {quantity} veces."
                    ),
                }
            )
        return warnings
