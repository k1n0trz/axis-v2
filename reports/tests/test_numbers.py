"""Lectura de numeros de hoja de calculo.

Regresion: habia cinco copias de `parse_decimal` que hacian
`str(value).replace(",", "")`, asi que "16,72" entraba a la base como 1672 y
"$ 16,72" como 0. Silencioso en los dos casos.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from reports.utils.numbers import normalize_header, parse_decimal, parse_quantity


class ParseDecimalTests(SimpleTestCase):
    def test_coma_decimal(self):
        # El caso que costaba un factor de cien.
        self.assertEqual(parse_decimal("16,72"), Decimal("16.72"))
        self.assertEqual(parse_decimal("16,7"), Decimal("16.7"))
        self.assertEqual(parse_decimal("0,5"), Decimal("0.5"))

    def test_punto_decimal(self):
        self.assertEqual(parse_decimal("16.72"), Decimal("16.72"))
        self.assertEqual(parse_decimal(" 16.72 "), Decimal("16.72"))

    def test_manda_el_ultimo_separador_cuando_hay_dos(self):
        self.assertEqual(parse_decimal("1.234,56"), Decimal("1234.56"))
        self.assertEqual(parse_decimal("1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_decimal("19.667.572,45"), Decimal("19667572.45"))

    def test_separador_repetido_es_de_miles(self):
        self.assertEqual(parse_decimal("1.234.567"), Decimal("1234567"))
        self.assertEqual(parse_decimal("1,234,567"), Decimal("1234567"))

    def test_tres_digitos_detras_se_leen_como_miles(self):
        # Ambiguo a proposito: en estas hojas los COP son enteros grandes.
        self.assertEqual(parse_decimal("1.234"), Decimal("1234"))
        self.assertEqual(parse_decimal("1,234"), Decimal("1234"))
        self.assertEqual(parse_decimal("105.967.985"), Decimal("105967985"))

    def test_simbolos_de_moneda_no_borran_la_linea(self):
        # Antes cada uno de estos devolvia 0 y la venta desaparecia.
        self.assertEqual(parse_decimal("$ 16,72"), Decimal("16.72"))
        self.assertEqual(parse_decimal("USD 16.72"), Decimal("16.72"))
        self.assertEqual(parse_decimal("COP 1.234.567"), Decimal("1234567"))
        self.assertEqual(parse_decimal("16,72 USD"), Decimal("16.72"))

    def test_negativos(self):
        self.assertEqual(parse_decimal("-16,72"), Decimal("-16.72"))
        self.assertEqual(parse_decimal("-1.234"), Decimal("-1234"))

    def test_numeros_nativos_pasan_tal_cual(self):
        self.assertEqual(parse_decimal(16.72), Decimal("16.72"))
        self.assertEqual(parse_decimal(3), Decimal("3"))
        self.assertEqual(parse_decimal(Decimal("16.72")), Decimal("16.72"))

    def test_lo_ilegible_devuelve_el_valor_por_defecto(self):
        for valor in ("B", "", "   ", None, "-", ".", ",", "sin dato"):
            with self.subTest(valor=valor):
                self.assertEqual(parse_decimal(valor), Decimal("0"))
        self.assertEqual(parse_decimal("B", default=Decimal("-1")), Decimal("-1"))

    def test_un_booleano_no_es_un_importe(self):
        self.assertEqual(parse_decimal(True), Decimal("0"))
        self.assertEqual(parse_decimal(False), Decimal("0"))


class ParseQuantityTests(SimpleTestCase):
    def test_cantidades_normales(self):
        self.assertEqual(parse_quantity("3"), 3)
        self.assertEqual(parse_quantity(3.0), 3)
        self.assertEqual(parse_quantity("3.0"), 3)

    def test_una_cantidad_con_coma_decimal_no_se_multiplica_por_diez(self):
        # Antes "3,0" devolvia 30.
        self.assertEqual(parse_quantity("3,0"), 3)
        self.assertEqual(parse_quantity("2,00"), 2)

    def test_lo_ilegible_cuenta_como_cero(self):
        for valor in ("B", "", None, "-1", 0):
            with self.subTest(valor=valor):
                self.assertEqual(parse_quantity(valor), 0)


class NormalizeHeaderTests(SimpleTestCase):
    def test_quita_acentos_y_normaliza(self):
        self.assertEqual(normalize_header("ENVÍO"), "envio")
        self.assertEqual(normalize_header("  Fecha  "), "fecha")
        self.assertEqual(normalize_header("CANTIDAD"), "cantidad")
        self.assertEqual(normalize_header(None), "")
