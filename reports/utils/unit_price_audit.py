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
TOLERANCIA = Decimal("0.02")


def _mediana(valores):
    ordenados = sorted(valores)
    medio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[medio]
    return (ordenados[medio - 1] + ordenados[medio]) / 2


class AuditorDePrecioUnitario:
    """Acumula filas y despues señala las que parecen traer el total de la linea.

    Uso:

        auditor = AuditorDePrecioUnitario()
        for fila in filas:
            auditor.registrar(producto, cantidad, valor, referencia=fecha)
        for aviso in auditor.sospechosas():
            ...
    """

    def __init__(self, tolerancia=TOLERANCIA):
        self.tolerancia = Decimal(str(tolerancia))
        self._filas = []
        self._por_producto = defaultdict(list)

    def registrar(self, producto, cantidad, valor, referencia="", en_rango=True):
        """Registra una fila.

        `en_rango=False` la usa solo para calibrar el precio del producto, sin
        reportarla. Sirve para alimentar el auditor con toda la hoja aunque la
        importacion cubra un solo dia: si el precio de referencia tuviera que
        estar en el mismo dia, casi nunca habria con que comparar.
        """
        nombre = " ".join(str(producto or "").split()).lower()
        try:
            valor = Decimal(str(valor))
        except Exception:
            return
        cantidad = int(cantidad or 0)
        if not nombre or valor <= 0:
            return
        if en_rango:
            self._filas.append((nombre, cantidad, valor, referencia))
        # Solo las lineas de una unidad sirven de referencia: ahi VALOR es el
        # precio unitario sin ambiguedad posible.
        if cantidad == 1:
            self._por_producto[nombre].append(valor)

    def _unitario_de_referencia(self, nombre):
        valores = self._por_producto.get(nombre)
        return _mediana(valores) if valores else None

    def sospechosas(self):
        """Devuelve un aviso por fila que parece traer el total de la linea."""
        avisos = []
        for nombre, cantidad, valor, referencia in self._filas:
            if cantidad < 2:
                continue
            referencia_unitaria = self._unitario_de_referencia(nombre)
            if not referencia_unitaria:
                continue
            esperado_como_total = referencia_unitaria * cantidad
            if esperado_como_total <= 0:
                continue
            desvio = abs(valor - esperado_como_total) / esperado_como_total
            if desvio > self.tolerancia:
                continue
            avisos.append(
                {
                    "producto": nombre,
                    "cantidad": cantidad,
                    "valor_en_la_hoja": valor,
                    "unitario_de_referencia": referencia_unitaria,
                    "referencia": referencia,
                    "sobrecosto": valor * cantidad - valor,
                    "mensaje": (
                        f"{referencia} {nombre}: VALOR {valor} con CANTIDAD {cantidad} parece ser el total "
                        f"de la linea, no el precio unitario ({referencia_unitaria} en otras filas del mismo "
                        f"producto). Multiplicarlo la contaria {cantidad} veces."
                    ),
                }
            )
        return avisos
