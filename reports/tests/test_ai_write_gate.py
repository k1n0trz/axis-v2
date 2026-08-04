"""Quien puede dejar que la IA escriba, y por donde pasa esa escritura."""
import json
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth.models import Group, Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from reports.ai.attachments import save_attachment
from reports.ai.permissions import IMPORT_PERMISSIONS, WRITE_GROUP, can_import_data, why_not_import
from reports.ai.tools import TOOLS
from reports.models import DailyChannelSale, IntegrationRun, UserProfile

MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="axis-test-gate-")


def _staff(username="alejo", superuser=False):
    usuario = User.objects.create_user(
        username=username, password="x", is_staff=True, is_superuser=superuser
    )
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    return usuario


def _en_el_grupo(usuario, con_permisos=True):
    grupo, _ = Group.objects.get_or_create(name=WRITE_GROUP)
    if con_permisos:
        for ruta in IMPORT_PERMISSIONS:
            grupo.permissions.add(Permission.objects.get(codename=ruta.split(".")[1]))
    usuario.groups.add(grupo)
    return User.objects.get(pk=usuario.pk)


def _archivo(user):
    libro = Workbook()
    pagina = libro.active
    pagina.title = "Ecuador"
    pagina.append(["FECHA", "PRODUCTO", "CANTIDAD", "VALOR", "MONEDA"])
    pagina.append(["2026-07-01", "Copa Uva", 2, "16,72", "USD"])
    buffer = BytesIO()
    libro.save(buffer)
    return save_attachment(user, SimpleUploadedFile("despachos.xlsx", buffer.getvalue()))[0]


class LlaveDeEscrituraTests(TestCase):
    def test_sin_grupo_nadie_escribe_ni_siendo_superusuario(self):
        # Ser superusuario no alcanza: la llave se da a mano.
        jefe = _staff("alejo", superuser=True)

        self.assertFalse(can_import_data(jefe))
        self.assertIn("no existe todavia", why_not_import(jefe))

    def test_en_el_grupo_y_con_permisos_si_escribe(self):
        usuario = _en_el_grupo(_staff("editrafficker"))

        self.assertTrue(can_import_data(usuario))
        self.assertEqual(why_not_import(usuario), "")

    def test_estar_en_el_grupo_sin_los_permisos_no_alcanza(self):
        # El grupo abre la puerta; el permiso dice que se puede mover adentro.
        usuario = _en_el_grupo(_staff("analista"), con_permisos=False)

        self.assertFalse(can_import_data(usuario))
        self.assertIn("faltan permisos", why_not_import(usuario))

    def test_quien_no_esta_en_el_grupo_recibe_el_motivo(self):
        _en_el_grupo(_staff("editrafficker"))
        ajeno = _staff("karen")

        self.assertFalse(can_import_data(ajeno))
        self.assertIn(WRITE_GROUP, why_not_import(ajeno))

    def test_cargar_no_es_una_herramienta_del_modelo(self):
        # La IA diagnostica y simula; el boton lo aprieta una persona.
        for nombre in TOOLS:
            self.assertNotIn("apply", nombre)
            self.assertNotIn("import_file", nombre)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL, DEEPSEEK_API_KEY="clave-de-prueba")
class EndpointDeCargaTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _en_el_grupo(_staff("alejo"))
        self.client.force_login(self.user)
        self.attachment = _archivo(self.user)

    def _cargar(self, **cuerpo):
        return self.client.post(
            reverse("reports:ai_attachment_import", args=[self.attachment.pk]),
            data=json.dumps(cuerpo),
            content_type="application/json",
        )

    def test_con_confirmacion_la_carga_escribe(self):
        antes = DailyChannelSale.objects.count()

        respuesta = self._cargar(confirm=True)

        self.assertEqual(respuesta.status_code, 200)
        self.assertGreater(DailyChannelSale.objects.count(), antes)
        self.assertIn("SI quedo escrito", respuesta.json()["imported"]["nota"])

    def test_sin_confirmacion_explicita_no_escribe_nada(self):
        antes = DailyChannelSale.objects.count()

        respuesta = self._cargar()

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(DailyChannelSale.objects.count(), antes)

    def test_quien_no_esta_en_el_grupo_recibe_403_y_no_escribe(self):
        antes = DailyChannelSale.objects.count()
        self.client.force_login(_staff("karen"))

        respuesta = self._cargar(confirm=True)

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(DailyChannelSale.objects.count(), antes)

    def test_no_se_puede_cargar_el_archivo_de_otro(self):
        otro = _en_el_grupo(_staff("editrafficker"))
        self.client.force_login(otro)

        self.assertEqual(self._cargar(confirm=True).status_code, 404)

    def test_la_carga_queda_en_la_bitacora_con_quien_la_lanzo(self):
        self._cargar(confirm=True)

        corrida = IntegrationRun.objects.filter(source__startswith="IA carga").first()
        self.assertIsNotNone(corrida)
        self.assertIn("alejo", corrida.command)
        self.assertIn("despachos.xlsx", corrida.summary)

    def test_la_simulacion_desde_el_widget_no_escribe(self):
        antes = DailyChannelSale.objects.count()

        respuesta = self.client.post(
            reverse("reports:ai_attachment_preview", args=[self.attachment.pk]),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(DailyChannelSale.objects.count(), antes)
        self.assertTrue(respuesta.json()["can_import"])

    def test_cargar_dos_veces_el_mismo_archivo_no_duplica(self):
        # Los importadores usan update_or_create sobre una clave unica real.
        self._cargar(confirm=True)
        filas = DailyChannelSale.objects.count()

        self._cargar(confirm=True)

        self.assertEqual(DailyChannelSale.objects.count(), filas)
