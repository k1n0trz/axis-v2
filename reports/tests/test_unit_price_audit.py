"""Guardia contra la convencion mezclada en la columna VALOR.

VALOR es precio por unidad y el importador lo multiplica por CANTIDAD, pero la hoja
de despachos tiene filas que ya traen el total calculado. En julio 2026 habia
cuatro, y multiplicarlas sumaba 177,49 USD de mas al mes; nadie las vio hasta que
el total no cuadro.

El auditor solo avisa. Corregir en el importador seria peor: el archivo fuente y
Axis dirian cosas distintas y nadie sabria cual creer.
"""
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from openpyxl import Workbook

from reports.models import BusinessUnit, Channel, Country
from reports.services.sales_dashboard import ensure_uva_catalogs
from reports.utils.unit_price_audit import UnitPriceAuditor


class AuditorTests(SimpleTestCase):
    def test_señala_la_fila_que_trae_el_total(self):
        auditor = UnitPriceAuditor()
        # Las filas de una unidad fijan el precio real del producto.
        auditor.record("Calzones M Moderado", 1, "16.72", reference="2026-07-01")
        auditor.record("Calzones M Moderado", 1, "16.72", reference="2026-07-02")
        # Esta trae 3 x 16.72 = 50.16 en VALOR, que es el caso real de julio.
        auditor.record("Calzones M Moderado", 3, "50.16", reference="2026-07-03")

        avisos = auditor.suspicious()

        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0]["quantity"], 3)
        self.assertEqual(avisos[0]["sheet_value"], Decimal("50.16"))
        self.assertEqual(avisos[0]["reference_unit_price"], Decimal("16.72"))
        self.assertIn("2026-07-03", avisos[0]["message"])

    def test_una_fila_correcta_no_se_señala(self):
        auditor = UnitPriceAuditor()
        auditor.record("Copa Uva talla A", 1, "21.57")
        auditor.record("Copa Uva talla A", 2, "21.57")  # precio unitario, bien

        self.assertEqual(auditor.suspicious(), [])

    def test_los_cuatro_casos_reales_de_julio(self):
        auditor = UnitPriceAuditor()
        for producto, unitario in (("Calzones M Moderado", "16.72"), ("Calzones M Leve", "17.01"), ("Copa Uva talla A", "21.57")):
            auditor.record(producto, 1, unitario)
        auditor.record("Calzones M Moderado", 3, "50.16", reference="07-03")
        auditor.record("Calzones M Moderado", 2, "34.02", reference="07-04")
        auditor.record("Copa Uva talla A", 2, "43.15", reference="07-07")
        auditor.record("Calzones M Leve", 3, "51.03", reference="07-04")

        referencias = sorted(w["reference"] for w in auditor.suspicious())

        self.assertEqual(referencias, ["07-03", "07-04", "07-04", "07-07"])

    def test_sin_una_fila_de_una_unidad_no_hay_con_que_comparar(self):
        # Prudente a proposito: mejor no avisar que inventar un precio de referencia.
        auditor = UnitPriceAuditor()
        auditor.record("Producto nuevo", 3, "50.16")

        self.assertEqual(auditor.suspicious(), [])

    def test_tolera_centavos_de_redondeo(self):
        auditor = UnitPriceAuditor()
        auditor.record("Calzones M Leve", 1, "17.01")
        auditor.record("Calzones M Leve", 3, "51.02")  # 3 x 17.01 = 51.03

        self.assertEqual(len(auditor.suspicious()), 1)

    def test_no_confunde_un_producto_mas_caro_con_un_total(self):
        auditor = UnitPriceAuditor()
        auditor.record("Kit completo", 1, "60.00")
        auditor.record("Kit completo", 2, "60.00")  # correcto
        auditor.record("Kit completo", 5, "63.00")  # ni 5x ni parecido

        self.assertEqual(auditor.suspicious(), [])

    def test_ignora_basura_sin_reventar(self):
        auditor = UnitPriceAuditor()
        for producto, cantidad, valor in (("", 1, "10"), ("X", 1, "B"), ("Y", 1, "0"), (None, 2, "5")):
            auditor.record(producto, cantidad, valor)

        self.assertEqual(auditor.suspicious(), [])


CABECERA = ["PRODUCTO", "FECHA", "Canal", "CANTIDAD", "VALOR", "ENVÍO", "Total COP"]


def libro(filas):
    wb = Workbook()
    ws = wb.active
    ws.title = "Ecuador"
    ws.append(CABECERA)
    for fila in filas:
        ws.append(fila)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


@override_settings(
    ONEDRIVE_CLIENT_ID="id",
    ONEDRIVE_CLIENT_SECRET="secreto",
    ONEDRIVE_TENANT_ID="inquilino",
)
class AvisoEnLaImportacionTests(TestCase):
    def setUp(self):
        ensure_uva_catalogs()
        self.unidad, _ = BusinessUnit.objects.get_or_create(slug="uva", defaults={"name": "Uva"})
        self.pais, _ = Country.objects.get_or_create(code="EC", defaults={"name": "Ecuador"})
        for nombre, slug in (("WhatsApp Ecuador", "whatsapp-uva-ec"), ("Ecommerce Uva", "ecommerce-uva")):
            Channel.objects.get_or_create(slug=slug, business_unit=self.unidad, defaults={"name": nombre})

    def _importar(self, filas):
        salida = StringIO()
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "despachos.xlsx"
            ruta.write_bytes(libro(filas).getvalue())
            call_command("import_ecuador_sales", str(ruta), "--sheet=Ecuador", stdout=salida)
        return salida.getvalue()

    def test_la_importacion_avisa_de_la_fila_sospechosa(self):
        filas = [
            ["Copa Menstrual Uva talla A", "2026-07-01", "pagina", 1, 21.57, 0, 79809],
            ["Copa Menstrual Uva talla A", "2026-07-07", "pagina", 2, 43.15, 0, 159655],
        ]

        salida = self._importar(filas)

        self.assertIn("parecen traer el TOTAL de la linea", salida)
        self.assertIn("Filas con VALOR sospechoso: 1", salida)

    def test_sin_filas_raras_no_molesta(self):
        filas = [
            ["Copa Menstrual Uva talla A", "2026-07-01", "pagina", 1, 21.57, 0, 79809],
            ["Copa Menstrual Uva talla A", "2026-07-07", "pagina", 2, 21.57, 0, 159618],
        ]

        salida = self._importar(filas)

        self.assertNotIn("parecen traer el TOTAL", salida)
        self.assertIn("Filas con VALOR sospechoso: 0", salida)


@override_settings(
    ONEDRIVE_CLIENT_ID="id",
    ONEDRIVE_CLIENT_SECRET="secreto",
    ONEDRIVE_TENANT_ID="inquilino",
)
class AvisoEnElSyncDiarioTests(TestCase):
    """El comando que corre el sync diario devuelve JSON, no warnings.

    Es `fetch_onedrive_excel`, no `import_ecuador_sales`, el que ejecuta
    sync_axis_daily_data. Si el aviso solo viviera en el importador manual, el
    camino automatico seguiria ciego.
    """

    CABECERA = ["PRODUCTO", "FECHA", "CENTRO DE COSTOS", "CANTIDAD", "VALOR", "ENVÍO"]

    def setUp(self):
        ensure_uva_catalogs()
        self.unidad, _ = BusinessUnit.objects.get_or_create(slug="uva", defaults={"name": "Uva"})
        self.pais, _ = Country.objects.get_or_create(code="EC", defaults={"name": "Ecuador"})
        for nombre, slug in (("WhatsApp Ecuador", "whatsapp-uva-ec"), ("Ecommerce Uva", "ecommerce-uva")):
            Channel.objects.get_or_create(slug=slug, business_unit=self.unidad, defaults={"name": nombre})

    def _correr(self, filas):
        import json as _json

        wb = Workbook()
        ws = wb.active
        ws.title = "Ecuador"
        ws.append(self.CABECERA)
        for fila in filas:
            ws.append(fila)
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        salida = StringIO()
        with patch("reports.management.commands.fetch_onedrive_excel.onedrive") as od:
            od.refresh_access_token.return_value = {"access_token": "t"}
            od.download_file_content_by_path.return_value = buffer
            call_command(
                "fetch_onedrive_excel",
                "--date", "2026-07-15",
                "--country", "EC",
                "--drive-path", "/despachos.xlsx",
                "--sheet", "Ecuador",
                "--default-currency", "USD",
                stdout=salida,
            )
        return _json.loads(salida.getvalue())

    def test_el_payload_incluye_las_filas_sospechosas(self):
        filas = [
            ["Copa Menstrual Uva talla A", "2026-07-15", "Whatsapp", 1, 21.57, 0],
            ["Copa Menstrual Uva talla A", "2026-07-15", "Whatsapp", 2, 43.15, 0],
        ]

        payload = self._correr(filas)

        self.assertEqual(len(payload["suspicious_unit_prices"]), 1)
        aviso = payload["suspicious_unit_prices"][0]
        self.assertEqual(aviso["quantity"], "2")
        self.assertIn("43.15", aviso["sheet_value"])

    def test_sin_filas_raras_la_lista_va_vacia(self):
        filas = [
            ["Copa Menstrual Uva talla A", "2026-07-15", "Whatsapp", 1, 21.57, 0],
            ["Copa Menstrual Uva talla A", "2026-07-15", "Whatsapp", 2, 21.57, 0],
        ]

        self.assertEqual(self._correr(filas)["suspicious_unit_prices"], [])
