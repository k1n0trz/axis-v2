"""Archivos que el usuario le pasa a la IA y siguen ahi la semana siguiente."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.ai.attachments import (
    MAX_ACTIVE_PER_USER,
    AttachmentError,
    forget_attachment,
    list_attachments,
    save_attachment,
)
from reports.ai.tools import run_tool
from reports.models import AiAttachment, UserProfile

MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="axis-test-media-")


def _staff(username):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    return usuario


def _excel(nombre="ventas.xlsx", contenido=b"PK\x03\x04 contenido de prueba"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/octet-stream")


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class GuardarArchivosTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff("alejo")

    def test_un_excel_se_guarda_con_su_nombre_original(self):
        attachment, era_nuevo = save_attachment(self.user, _excel("Despachos Julio.xlsx"))

        self.assertTrue(era_nuevo)
        self.assertEqual(attachment.original_name, "Despachos_Julio.xlsx")
        self.assertGreater(attachment.size_bytes, 0)

    def test_subir_el_mismo_archivo_dos_veces_no_duplica(self):
        primero, _ = save_attachment(self.user, _excel())
        segundo, era_nuevo = save_attachment(self.user, _excel())

        self.assertEqual(primero.pk, segundo.pk)
        self.assertFalse(era_nuevo)
        self.assertEqual(AiAttachment.objects.filter(user=self.user).count(), 1)

    def test_el_mismo_nombre_con_otro_contenido_si_es_otro_archivo(self):
        save_attachment(self.user, _excel("ventas.xlsx", b"PK contenido uno"))
        save_attachment(self.user, _excel("ventas.xlsx", b"PK contenido dos distinto"))

        self.assertEqual(AiAttachment.objects.filter(user=self.user).count(), 2)

    def test_dos_personas_pueden_subir_el_mismo_archivo(self):
        otro = _staff("otra-persona")

        save_attachment(self.user, _excel())
        save_attachment(otro, _excel())

        self.assertEqual(AiAttachment.objects.count(), 2)

    def test_una_extension_que_no_esta_permitida_se_rechaza(self):
        with self.assertRaises(AttachmentError) as contexto:
            save_attachment(self.user, SimpleUploadedFile("pagina.html", b"<h1>hola</h1>"))

        self.assertIn("No acepto archivos", str(contexto.exception))

    def test_el_content_type_del_navegador_no_decide_nada(self):
        # Un .html anunciado como CSV no debe entrar: ese encabezado lo pone el cliente.
        with self.assertRaises(AttachmentError):
            save_attachment(
                self.user, SimpleUploadedFile("pagina.html", b"<h1>hola</h1>", content_type="text/csv")
            )

    def test_el_tipo_guardado_sale_de_la_extension_validada(self):
        attachment, _ = save_attachment(
            self.user, SimpleUploadedFile("datos.csv", b"a;b;c", content_type="application/x-mentira")
        )

        self.assertEqual(attachment.content_type, "text/csv")

    def test_un_archivo_vacio_se_rechaza(self):
        with self.assertRaises(AttachmentError) as contexto:
            save_attachment(self.user, SimpleUploadedFile("vacio.csv", b""))

        self.assertIn("vacio", str(contexto.exception))

    @override_settings(AI_ATTACHMENT_MAX_BYTES=10)
    def test_un_archivo_muy_grande_se_rechaza(self):
        with self.assertRaises(AttachmentError) as contexto:
            save_attachment(self.user, _excel("grande.xlsx", b"x" * 500))

        self.assertIn("MB", str(contexto.exception))

    def test_pasar_del_techo_retira_los_mas_viejos(self):
        for indice in range(MAX_ACTIVE_PER_USER + 2):
            save_attachment(self.user, _excel(f"archivo-{indice}.csv", f"contenido {indice}".encode()))

        self.assertEqual(list_attachments(self.user).count(), MAX_ACTIVE_PER_USER)
        # No se borra nada: quedan inactivos.
        self.assertEqual(AiAttachment.objects.filter(user=self.user).count(), MAX_ACTIVE_PER_USER + 2)

    def test_volver_a_subir_algo_retirado_lo_reactiva(self):
        attachment, _ = save_attachment(self.user, _excel())
        forget_attachment(self.user, attachment.pk)

        de_nuevo, era_nuevo = save_attachment(self.user, _excel())

        self.assertEqual(de_nuevo.pk, attachment.pk)
        self.assertFalse(era_nuevo)
        self.assertTrue(AiAttachment.objects.get(pk=attachment.pk).is_active)

    def test_nadie_puede_retirar_el_archivo_de_otro(self):
        attachment, _ = save_attachment(self.user, _excel())
        otro = _staff("otra-persona")

        self.assertEqual(forget_attachment(otro, attachment.pk), 0)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL, DEEPSEEK_API_KEY="clave-de-prueba")
class EndpointsDeArchivosTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff("alejo")
        self.client.force_login(self.user)

    def _subir(self, archivo=None):
        return self.client.post(
            reverse("reports:ai_attachment_upload"), {"file": archivo or _excel()}
        )

    def test_subir_y_listar(self):
        respuesta = self._subir()

        self.assertEqual(respuesta.status_code, 200)
        listado = self.client.get(reverse("reports:ai_attachments")).json()
        self.assertEqual(len(listado["attachments"]), 1)
        self.assertEqual(listado["attachments"][0]["name"], "ventas.xlsx")

    def test_subir_sin_archivo_responde_400(self):
        respuesta = self.client.post(reverse("reports:ai_attachment_upload"), {})

        self.assertEqual(respuesta.status_code, 400)

    def test_una_extension_rechazada_devuelve_el_motivo_al_usuario(self):
        respuesta = self._subir(SimpleUploadedFile("pagina.html", b"<h1>x</h1>"))

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("No acepto archivos", respuesta.json()["detail"])

    def test_el_archivo_queda_atado_a_la_conversacion_en_curso(self):
        self._subir()

        attachment = AiAttachment.objects.get(user=self.user)
        self.assertIsNotNone(attachment.conversation)

    def test_el_dueno_puede_descargarlo(self):
        self._subir()
        attachment = AiAttachment.objects.get(user=self.user)

        respuesta = self.client.get(reverse("reports:ai_attachment_download", args=[attachment.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("ventas.xlsx", respuesta["Content-Disposition"])

    def test_otro_usuario_del_equipo_no_puede_descargarlo(self):
        # Es la razon de no usar protected_media: esa vista solo exige sesion de staff.
        self._subir()
        attachment = AiAttachment.objects.get(user=self.user)

        self.client.force_login(_staff("otra-persona"))
        respuesta = self.client.get(reverse("reports:ai_attachment_download", args=[attachment.pk]))

        self.assertEqual(respuesta.status_code, 404)

    def test_un_archivo_retirado_ya_no_se_descarga(self):
        self._subir()
        attachment = AiAttachment.objects.get(user=self.user)
        self.client.post(reverse("reports:ai_attachment_forget", args=[attachment.pk]))

        respuesta = self.client.get(reverse("reports:ai_attachment_download", args=[attachment.pk]))

        self.assertEqual(respuesta.status_code, 404)

    def test_sin_sesion_no_hay_subida(self):
        self.client.logout()

        self.assertEqual(self._subir().status_code, 403)

    def test_la_lista_es_por_usuario(self):
        self._subir()
        self.client.force_login(_staff("otra-persona"))

        listado = self.client.get(reverse("reports:ai_attachments")).json()

        self.assertEqual(listado["attachments"], [])


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class HerramientaDeArchivosTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = _staff("alejo")

    def test_la_ia_ve_el_inventario_pero_no_el_contenido(self):
        save_attachment(self.user, _excel("Despachos.xlsx"))

        datos = run_tool(self.user, "list_my_files", {})

        self.assertEqual(len(datos["archivos"]), 1)
        self.assertEqual(datos["archivos"][0]["nombre"], "Despachos.xlsx")
        self.assertIn("no puedes leer el contenido", datos["nota"])

    def test_la_ia_no_ve_los_archivos_de_otro(self):
        save_attachment(_staff("otra-persona"), _excel())

        datos = run_tool(self.user, "list_my_files", {})

        self.assertEqual(datos["archivos"], [])


class AlmacenamientoTests(TestCase):
    """Donde terminan los archivos. En Cloud Run el disco se borra al reiniciar."""

    def test_el_storage_por_defecto_usa_el_bucket_cuando_esta_configurado(self):
        from django.conf import settings

        backend = settings.STORAGES["default"]["BACKEND"]
        if getattr(settings, "GS_BUCKET_NAME", ""):
            self.assertIn("gcloud", backend.lower())
        else:
            # Sin bucket configurado (local y tests) el disco esta bien.
            self.assertIn("filesystem", backend.lower())

    def test_la_ruta_del_adjunto_no_lleva_el_nombre_de_otro_usuario(self):
        import tempfile

        with override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="axis-ruta-")):
            user = _staff("alejo")
            attachment, _ = save_attachment(user, _excel("Reporte Confidencial.xlsx"))

        # El nombre en el bucket es el hash, no el titulo del archivo.
        self.assertNotIn("Confidencial", attachment.file.name)
        self.assertIn(f"{user.pk}/", attachment.file.name)
