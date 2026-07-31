"""Un precio unitario debe multiplicarse por la cantidad de la linea.

Regresion: el importador leia VALOR (precio por unidad) como si fuera el total
de la linea, asi que toda venta de 2 o mas unidades se contaba como una sola.
En julio 2026 eso dejaba fuera 809,89 USD de Ecuador (~15% del mes).
"""
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook

from reports.models import BusinessUnit, Channel, Country, DailyProductCategorySale
from reports.services.sales_dashboard import ensure_uva_catalogs


def libro(filas, cabecera):
    wb = Workbook()
    ws = wb.active
    ws.title = "Ecuador"
    ws.append(cabecera)
    for fila in filas:
        ws.append(fila)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


CABECERA = ["PRODUCTO", "FECHA", "CENTRO DE COSTOS", "CANTIDAD", "VALOR", "ENVÍO"]


@override_settings(
    ONEDRIVE_CLIENT_ID="id",
    ONEDRIVE_CLIENT_SECRET="secreto",
    ONEDRIVE_TENANT_ID="inquilino",
    ONEDRIVE_ECUADOR_FILE_PATH="/despachos.xlsx",
    ONEDRIVE_ECUADOR_SHEET="Ecuador",
)
class PrecioUnitarioPorCantidadTests(TestCase):
    def setUp(self):
        # El importador necesita marcas, paises, canales y categorias de
        # producto ya existentes; si falta alguno, descarta la fila en silencio.
        ensure_uva_catalogs()
        self.unidad, _ = BusinessUnit.objects.get_or_create(slug="uva", defaults={"name": "Uva"})
        self.pais, _ = Country.objects.get_or_create(code="EC", defaults={"name": "Ecuador"})
        for nombre, slug in (("WhatsApp Ecuador", "whatsapp-uva-ec"), ("Ecommerce Uva", "ecommerce-uva")):
            Channel.objects.get_or_create(slug=slug, business_unit=self.unidad, defaults={"name": nombre})

    def _importar(self, filas, cabecera=CABECERA, pais="EC", fecha="2026-07-15"):
        buffer = libro(filas, cabecera)
        with patch("reports.management.commands.fetch_onedrive_excel.onedrive") as od:
            od.refresh_access_token.return_value = {"access_token": "t"}
            od.download_file_content_by_path.return_value = buffer
            # Sin --sync-axis el comando solo reporta el payload, no escribe.
            call_command(
                "fetch_onedrive_excel",
                "--date", fecha,
                "--country", pais,
                "--sheet", "Ecuador",
                "--sync-axis",
                stdout=StringIO(),
            )

    def _usd(self):
        """Importe original en USD registrado por el importador."""
        return sum((v.original_amount or Decimal("0")) for v in DailyProductCategorySale.objects.all())

    def _cop(self):
        return sum((v.sales_amount or Decimal("0")) for v in DailyProductCategorySale.objects.all())

    def test_multiplica_el_precio_unitario_por_la_cantidad(self):
        # 3 unidades a 16,72 USD = 50,16 USD, no 16,72.
        self._importar([["Calzones menstruales", date(2026, 7, 15), "Whatsapp", 3, 16.72, 0]])
        self.assertEqual(self._usd(), Decimal("50.16"))
        self.assertEqual(self._cop(), Decimal("185592.00"))

    def test_suma_el_envio_una_sola_vez(self):
        # El envio es por linea, no por unidad: 2 x 5,99 + 3,50 = 15,48.
        self._importar([["Cubrepezones", date(2026, 7, 15), "Pagina", 2, 5.99, 3.50]])
        self.assertEqual(self._usd(), Decimal("15.48"))

    def test_cantidad_uno_no_cambia_el_importe(self):
        self._importar([["Copa Menstrual Uva talla A", date(2026, 7, 15), "Whatsapp", 1, 21.57, 0]])
        self.assertEqual(self._usd(), Decimal("21.57"))

    def test_cantidad_ilegible_cuenta_como_una_unidad(self):
        # En el archivo real hay una fila con CANTIDAD = "B".
        self._importar([["Copa Menstrual Uva talla B", date(2026, 7, 15), "Whatsapp", "B", 20.37, 0]])
        self.assertEqual(self._usd(), Decimal("20.37"))

    def test_una_columna_de_total_no_se_multiplica(self):
        # Si la hoja trae VENTAS (total de linea ya calculado), multiplicarlo
        # por la cantidad triplicaria el importe. Debe quedarse en 100000.
        cabecera = ["PRODUCTO", "FECHA", "CENTRO DE COSTOS", "CANTIDAD", "VENTAS"]
        self._importar([["Copa Menstrual Uva talla A", date(2026, 7, 15), "Whatsapp", 3, 100000]], cabecera=cabecera)
        self.assertEqual(self._usd(), Decimal("100000.00"))
        self.assertNotEqual(self._usd(), Decimal("300000.00"))

    def test_la_cantidad_se_sigue_registrando_aparte(self):
        self._importar([["Calzones menstruales", date(2026, 7, 15), "Whatsapp", 3, 16.72, 0]])
        self.assertEqual(sum(v.quantity or 0 for v in DailyProductCategorySale.objects.all()), 3)
