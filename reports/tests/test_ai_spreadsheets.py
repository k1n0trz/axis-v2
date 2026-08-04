"""Diagnostico y vista previa de un Excel subido al asistente."""
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from openpyxl import Workbook

from reports.ai.attachments import save_attachment
from reports.ai.spreadsheets import (
    ImportNotPossible,
    describe_attachment,
    match_shape,
    preview_import,
)
from reports.ai.tools import run_tool
from reports.models import DailyChannelSale, DailyProductCategorySale, UserProfile

MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="axis-test-hojas-")


def _staff(username="alejo"):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    return usuario


def _libro(filas, cabecera=("FECHA", "PRODUCTO", "CANTIDAD", "VALOR"), fila_de_cabecera=1, hoja="Ecuador"):
    """Un Excel de verdad, con la cabecera donde se pida."""
    libro = Workbook()
    pagina = libro.active
    pagina.title = hoja
    for _ in range(fila_de_cabecera - 1):
        pagina.append([])
    pagina.append(list(cabecera))
    for fila in filas:
        pagina.append(list(fila))
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _subir(user, contenido, nombre="despachos.xlsx"):
    return save_attachment(user, SimpleUploadedFile(nombre, contenido))[0]


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class DescribirArchivoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff()

    def test_encuentra_la_cabecera_y_las_columnas(self):
        contenido = _libro([("2026-07-01", "Copa Uva", 2, "16,72")])

        datos = describe_attachment(_subir(self.user, contenido))

        hoja = datos["hojas"][0]
        self.assertEqual(hoja["fila_de_cabecera"], 1)
        self.assertIn("producto", hoja["columnas"])
        self.assertIn("cantidad", hoja["columnas"])

    def test_encuentra_la_cabecera_aunque_este_en_la_fila_14(self):
        # Las hojas de despachos la traen ahi: asumir la fila 1 descartaba el archivo.
        contenido = _libro([("2026-07-01", "Copa Uva", 2, "16,72")], fila_de_cabecera=14)

        datos = describe_attachment(_subir(self.user, contenido))

        self.assertEqual(datos["hojas"][0]["fila_de_cabecera"], 14)

    def test_reconoce_la_forma_de_despachos(self):
        contenido = _libro([("2026-07-01", "Copa Uva", 2, "16,72")])

        datos = describe_attachment(_subir(self.user, contenido))

        self.assertIsNotNone(datos["hojas"][0]["forma_reconocida"])
        self.assertIn("VALOR es precio unitario", datos["hojas"][0]["nota_de_la_forma"])

    def test_una_hoja_sin_las_columnas_necesarias_no_tiene_forma(self):
        contenido = _libro(
            [("algo", "otra cosa", "mas")], cabecera=("COLUMNA A", "COLUMNA B", "COLUMNA C")
        )

        datos = describe_attachment(_subir(self.user, contenido))

        self.assertIsNone(datos["hojas"][0]["forma_reconocida"])

    def test_un_csv_todavia_no_se_mira_por_dentro(self):
        attachment = _subir(self.user, b"fecha;producto;cantidad", nombre="datos.csv")

        datos = describe_attachment(attachment)

        self.assertIn("solo puedo mirar dentro", datos["error"])

    def test_la_muestra_no_va_vacia(self):
        contenido = _libro([("2026-07-01", "Copa Uva", 2, "16,72"), ("2026-07-02", "Panty", 1, "9,90")])

        datos = describe_attachment(_subir(self.user, contenido))

        self.assertEqual(len(datos["hojas"][0]["muestra"]), 2)


class FormasConocidasTests(TestCase):
    def test_faltando_una_columna_obligatoria_no_encaja(self):
        self.assertIsNone(match_shape({"fecha", "producto"}))

    def test_con_las_obligatorias_encaja(self):
        self.assertIsNotNone(match_shape({"fecha", "producto", "cantidad"}))

    def test_gana_la_forma_con_mas_columnas_opcionales(self):
        forma = match_shape({"fecha", "producto", "cantidad", "valor", "moneda", "centro de costos"})

        self.assertEqual(forma["key"], "despachos_ecuador")


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class VistaPreviaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff()
        self.attachment = _subir(
            self.user,
            _libro([
                ("2026-07-01", "Copa Uva", 2, "16,72"),
                ("2026-07-02", "Copa Uva", 1, "16,72"),
            ]),
        )

    def test_la_vista_previa_no_deja_nada_escrito(self):
        # Es la garantia del modulo: corre el importador real y revierte.
        antes_canal = DailyChannelSale.objects.count()
        antes_categoria = DailyProductCategorySale.objects.count()

        preview_import(self.attachment)

        self.assertEqual(DailyChannelSale.objects.count(), antes_canal)
        self.assertEqual(DailyProductCategorySale.objects.count(), antes_categoria)

    def test_la_vista_previa_reporta_el_comando_que_se_correria(self):
        resultado = preview_import(self.attachment)

        self.assertIn("fetch_onedrive_excel", resultado["comando"])
        self.assertIn("--country EC", resultado["comando"])

    def test_la_vista_previa_dice_que_es_una_simulacion(self):
        resultado = preview_import(self.attachment)

        self.assertIn("Nada quedo escrito", resultado["nota"])

    def test_el_diff_trae_las_tres_tablas(self):
        resultado = preview_import(self.attachment)

        self.assertEqual(
            set(resultado["cambios"]),
            {"ventas_por_canal", "ventas_por_categoria", "inversion"},
        )

    def test_el_diff_no_es_cero_cuando_el_archivo_trae_ventas(self):
        # Sin esta prueba, un importador que no importara nada dejaria pasar la de
        # "no deja nada escrito" sin que nadie note que la carga es un no-op.
        resultado = preview_import(self.attachment)

        self.assertGreater(resultado["cambios"]["ventas_por_canal"]["filas_nuevas"], 0)
        self.assertGreater(resultado["cambios"]["ventas_por_canal"]["cambio_de_monto"], 0)

    def test_un_archivo_de_ecuador_no_cae_en_el_canal_de_colombia(self):
        resultado = preview_import(self.attachment)

        self.assertIn("--channel-slug whatsapp-uva-ec", resultado["comando"])

    def test_la_vista_previa_informa_el_periodo_que_trae_el_archivo(self):
        resultado = preview_import(self.attachment)

        self.assertEqual(resultado["periodo_del_archivo"], "2026-07-01 a 2026-07-02")

    def test_un_archivo_sin_forma_conocida_se_rechaza_con_motivo(self):
        sin_forma = _subir(
            self.user,
            _libro([("x", "y", "z")], cabecera=("ALFA", "BETA", "GAMMA")),
            nombre="raro.xlsx",
        )

        with self.assertRaises(ImportNotPossible) as contexto:
            preview_import(sin_forma)

        self.assertIn("Ninguna hoja", str(contexto.exception))


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class HerramientasDeHojasTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff()
        self.attachment = _subir(self.user, _libro([("2026-07-01", "Copa Uva", 2, "16,72")]))

    def test_describe_file_funciona_por_id(self):
        datos = run_tool(self.user, "describe_file", {"attachment_id": self.attachment.pk})

        self.assertEqual(datos["archivo"], "despachos.xlsx")

    def test_no_se_puede_mirar_el_archivo_de_otro(self):
        otro = _staff("otra-persona")

        datos = run_tool(otro, "describe_file", {"attachment_id": self.attachment.pk})

        self.assertIn("No encuentro ese archivo", datos["error"])

    def test_preview_file_import_devuelve_el_diff(self):
        datos = run_tool(self.user, "preview_file_import", {"attachment_id": self.attachment.pk})

        self.assertIn("cambios", datos)
        self.assertIn("Nada quedo escrito", datos["nota"])

    def test_un_id_que_no_existe_no_tumba_la_herramienta(self):
        datos = run_tool(self.user, "describe_file", {"attachment_id": 999999})

        self.assertIn("No encuentro ese archivo", datos["error"])


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class ArchivoQueYaNoEstaTests(TestCase):
    """La fila y el objeto del storage pueden divergir. Salio en una prueba real."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff()

    def test_si_el_contenido_desaparecio_se_avisa_en_vez_de_estallar(self):
        attachment = _subir(self.user, _libro([("2026-07-01", "Copa Uva", 2, "16,72")]))
        attachment.file.storage.delete(attachment.file.name)

        datos = run_tool(self.user, "describe_file", {"attachment_id": attachment.pk})

        self.assertIn("ya no esta guardado", datos["error"])

    def test_la_vista_previa_tambien_avisa_en_vez_de_estallar(self):
        attachment = _subir(self.user, _libro([("2026-07-01", "Copa Uva", 2, "16,72")]))
        attachment.file.storage.delete(attachment.file.name)

        datos = run_tool(self.user, "preview_file_import", {"attachment_id": attachment.pk})

        self.assertIn("ya no esta guardado", datos["error"])

    def test_volver_a_subirlo_repara_la_fila_en_vez_de_duplicarla(self):
        contenido = _libro([("2026-07-01", "Copa Uva", 2, "16,72")])
        attachment = _subir(self.user, contenido)
        attachment.file.storage.delete(attachment.file.name)

        de_nuevo = _subir(self.user, contenido)

        self.assertEqual(de_nuevo.pk, attachment.pk)
        self.assertTrue(de_nuevo.file.storage.exists(de_nuevo.file.name))
