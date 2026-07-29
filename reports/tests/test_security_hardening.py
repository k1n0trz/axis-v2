from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.forms import AttachmentUploadForm, OperationalGoalTaskUpdateForm
from reports.sanitizers import sanitize_rich_text
from reports.services.sales_dashboard import geo_location_key


class SanitizeRichTextTests(TestCase):
    def test_conserva_formato_basico_y_enlaces_seguros(self):
        html = '<p>Avance <strong>listo</strong>. <a href="https://helti.com.co">Ver</a></p>'
        self.assertEqual(sanitize_rich_text(html), html)

    def test_elimina_script_y_su_contenido(self):
        self.assertEqual(sanitize_rich_text("<script>alert(1)</script>hola"), "hola")

    def test_elimina_handlers_sin_comillas(self):
        # El saneador anterior por regex exigia comillas y dejaba pasar esto.
        for payload in (
            "<svg onload=alert(1)>",
            "<img src=x onerror=alert(1)>",
            "<div onmouseover=alert(1)>texto</div>",
        ):
            resultado = sanitize_rich_text(payload)
            self.assertNotIn("onload", resultado)
            self.assertNotIn("onerror", resultado)
            self.assertNotIn("onmouseover", resultado)

    def test_descarta_href_con_esquema_peligroso(self):
        for payload in (
            '<a href="javascript:alert(1)">x</a>',
            '<a href="java\nscript:alert(1)">x</a>',
            '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
        ):
            self.assertNotIn("href", sanitize_rich_text(payload))

    def test_escapa_texto_plano(self):
        self.assertEqual(sanitize_rich_text("5 < 10 & 3 > 1"), "5 &lt; 10 &amp; 3 &gt; 1")

    def test_no_rompe_con_llaves(self):
        # format_html trataba este texto como cadena de formato y devolvia 500.
        self.assertEqual(sanitize_rich_text("config {valor} lista"), "config {valor} lista")

    def test_cierra_marcado_desbalanceado(self):
        self.assertEqual(sanitize_rich_text("<p>hola"), "<p>hola</p>")


class OperationalGoalTaskFormTests(TestCase):
    def test_limpia_el_campo_al_validar(self):
        form = OperationalGoalTaskUpdateForm(data={"employee_response": "<b>ok</b><script>alert(1)</script>"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["employee_response"], "<b>ok</b>")


class AttachmentUploadValidationTests(TestCase):
    def _form(self, filename, size=1024):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils.datastructures import MultiValueDict

        upload = SimpleUploadedFile(filename, b"x" * size)
        return AttachmentUploadForm(data={}, files=MultiValueDict({"files": [upload]}))

    def test_rechaza_extension_no_permitida(self):
        form = self._form("payload.html")
        self.assertFalse(form.is_valid())
        self.assertIn("files", form.errors)

    def test_rechaza_archivo_demasiado_grande(self):
        form = self._form("informe.pdf", size=26 * 1024 * 1024)
        self.assertFalse(form.is_valid())
        self.assertIn("files", form.errors)

    def test_acepta_extension_permitida(self):
        form = self._form("informe.pdf")
        self.assertTrue(form.is_valid(), form.errors)

    def test_acepta_varios_archivos(self):
        # Regresion: el widget multiple entregaba una lista que FileField
        # rechazaba, asi que ninguna subida llegaba a validar.
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils.datastructures import MultiValueDict

        uploads = [SimpleUploadedFile("a.pdf", b"a"), SimpleUploadedFile("b.xlsx", b"b")]
        form = AttachmentUploadForm(data={}, files=MultiValueDict({"files": uploads}))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data["files"]), 2)

    def test_rechaza_el_lote_si_un_archivo_no_es_valido(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils.datastructures import MultiValueDict

        uploads = [SimpleUploadedFile("ok.pdf", b"a"), SimpleUploadedFile("payload.svg", b"b")]
        form = AttachmentUploadForm(data={}, files=MultiValueDict({"files": uploads}))
        self.assertFalse(form.is_valid())


class GeoLocationKeyTests(TestCase):
    def test_unifica_zonas_con_y_sin_calificativo(self):
        self.assertEqual(geo_location_key("Guayas Province"), geo_location_key("Guayas"))
        self.assertEqual(geo_location_key("Manabi Province"), geo_location_key("Manabí"))
        self.assertEqual(geo_location_key("Provincia de Azuay"), geo_location_key("Azuay"))
        self.assertEqual(geo_location_key("Departamento de Antioquia"), geo_location_key("Antioquia"))

    def test_state_of_mexico_usa_el_alias_existente(self):
        self.assertEqual(geo_location_key("State of Mexico"), geo_location_key("Estado de Mexico"))

    def test_conserva_los_alias_previos(self):
        self.assertEqual(geo_location_key("Bogota D.C."), "bogota")
        self.assertEqual(geo_location_key("Mexico City"), "distrito-federal")
        self.assertEqual(geo_location_key("CDMX"), "distrito-federal")

    def test_no_vacia_nombres_que_son_solo_calificativo(self):
        self.assertTrue(geo_location_key("Region"))


class OpenRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("empleado", password="clave-larga-123", is_staff=True)
        self.client.force_login(self.user)

    def _task(self):
        from datetime import date

        from reports.models import BusinessUnit, OperationalGoalTask, SalesTarget

        unit = BusinessUnit.objects.create(name="Uva")
        target = SalesTarget.objects.create(
            user=self.user,
            business_unit=unit,
            date_start=date(2026, 7, 1),
            date_end=date(2026, 7, 31),
            target_amount=1000,
        )
        return OperationalGoalTask.objects.create(
            sales_target=target,
            assigned_by=self.user,
            assigned_to=self.user,
            title="Revisar pauta",
        )

    def test_actualizar_tarea_no_redirige_a_dominio_externo(self):
        response = self.client.post(
            reverse("reports:operational_task_update", args=[self._task().pk]),
            {"employee_response": "listo", "next": "https://evil.example.com/robo"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response["Location"])

    def test_actualizar_tarea_sanea_la_respuesta_guardada(self):
        task = self._task()
        self.client.post(
            reverse("reports:operational_task_update", args=[task.pk]),
            {"employee_response": '<b>ok</b><img src=x onerror=alert(1)>'},
        )
        task.refresh_from_db()
        self.assertNotIn("onerror", task.employee_response)


class AdminExportPermissionTests(TestCase):
    def test_staff_sin_permiso_no_puede_exportar(self):
        user = User.objects.create_user("limitado", password="clave-larga-123", is_staff=True)
        self.client.force_login(user)
        response = self.client.get("/admin/reports/dailychannelsale/exportar-excel-universal/")
        self.assertIn(response.status_code, (302, 403))
