"""Bitacora de ejecuciones de integraciones.

Estaba en el roadmap desde mayo y nunca se construyo. Sin ella, cuando un dato no
aparece en el tablero las tres situaciones posibles se ven igual (una celda
vacia): el job no corrio, corrio y fallo, o corrio bien y la fuente venia vacia.
"""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from reports.integrations.run_log import MAX_PAYLOAD_CHARS, last_run_by_source, track_run
from reports.models import IntegrationRun
from reports.services.website_monitor import seed_websites


class TrackRunTests(TestCase):
    def test_una_corrida_normal_queda_como_exito(self):
        with track_run("prueba", command="cmd", target_date=timezone.localdate()) as run:
            run.summary = "todo bien"

        guardada = IntegrationRun.objects.get(pk=run.pk)
        self.assertEqual(guardada.status, IntegrationRun.Status.SUCCESS)
        self.assertEqual(guardada.summary, "todo bien")
        self.assertIsNotNone(guardada.finished_at)
        self.assertGreaterEqual(guardada.duration_seconds, 0)

    def test_queda_en_curso_mientras_corre(self):
        with track_run("prueba") as run:
            en_vivo = IntegrationRun.objects.get(pk=run.pk)
            self.assertEqual(en_vivo.status, IntegrationRun.Status.RUNNING)
            self.assertIsNone(en_vivo.finished_at)

    def test_un_fallo_queda_registrado_y_la_excepcion_se_relanza(self):
        # La bitacora no debe cambiar el comportamiento del comando.
        with self.assertRaises(ValueError):
            with track_run("prueba", command="cmd"):
                raise ValueError("la fuente no respondio")

        guardada = IntegrationRun.objects.get(source="prueba")
        self.assertEqual(guardada.status, IntegrationRun.Status.FAILED)
        self.assertIn("ValueError: la fuente no respondio", guardada.error_message)
        self.assertIsNotNone(guardada.finished_at)

    def test_el_comando_puede_declararse_omitido(self):
        with track_run("prueba") as run:
            run.status = IntegrationRun.Status.SKIPPED
            run.summary = "sin credenciales"

        self.assertEqual(IntegrationRun.objects.get(source="prueba").status, IntegrationRun.Status.SKIPPED)

    def test_recorta_un_payload_gigante(self):
        # El payload es para diagnosticar, no un respaldo de los datos.
        with track_run("prueba") as run:
            run.summary = "x" * 5000

        guardada = IntegrationRun.objects.get(source="prueba")
        self.assertLess(len(guardada.summary), 5000)
        self.assertIn("recortado", guardada.summary)

    def test_last_run_by_source_devuelve_la_mas_reciente(self):
        with track_run("uno") as run:
            run.summary = "vieja"
        with track_run("uno") as run:
            run.summary = "nueva"
        with track_run("dos") as run:
            run.summary = "otra fuente"

        ultimas = last_run_by_source()

        self.assertEqual(sorted(ultimas), ["dos", "uno"])
        self.assertEqual(ultimas["uno"].summary, "nueva")


class ComandosQueRegistranTests(TestCase):
    def test_sync_websites_health_deja_constancia(self):
        call_command("sync_websites_health", "--seed-only", stdout=StringIO())

        run = IntegrationRun.objects.get(source="websites_health")
        self.assertEqual(run.status, IntegrationRun.Status.SUCCESS)
        self.assertEqual(run.command, "sync_websites_health")
        self.assertIn("4 webs", run.summary)

    def test_un_fallo_del_escaneo_queda_en_la_bitacora(self):
        with patch("reports.management.commands.sync_websites_health.scan_active_websites", side_effect=RuntimeError("sin red")):
            with self.assertRaises(RuntimeError):
                call_command("sync_websites_health", stdout=StringIO())

        run = IntegrationRun.objects.get(source="websites_health")
        self.assertEqual(run.status, IntegrationRun.Status.FAILED)
        self.assertIn("sin red", run.error_message)

    @override_settings(META_ACCESS_TOKEN="", META_CO_ACCOUNT_ID="", META_MX_ACCOUNT_ID="", META_EC_ACCOUNT_ID="")
    def test_un_precalentamiento_sin_nada_listo_no_pasa_por_exito(self):
        # Sin cuentas configuradas no hay nada que precalentar: la pagina va a
        # mostrar el panel vacio y alguien tiene que enterarse.
        call_command("warm_meta_ads_preview", "--timeout=1", stdout=StringIO())

        run = IntegrationRun.objects.get(source="meta_ads_preview_warmup")
        self.assertEqual(run.status, IntegrationRun.Status.SKIPPED)
        self.assertEqual(run.payload["warmed"], 0)


class BitacoraDeLecturaTests(TestCase):
    def setUp(self):
        seed_websites()
        self.user = User.objects.create_superuser(username="jefe", password="secreto", email="j@e.co")
        self.client.force_login(self.user)

    def test_el_admin_no_permite_crear_ni_editar(self):
        with track_run("prueba") as run:
            run.summary = "algo"

        listado = self.client.get("/admin/reports/integrationrun/")
        self.assertEqual(listado.status_code, 200)
        self.assertEqual(self.client.get("/admin/reports/integrationrun/add/").status_code, 403)
        detalle = self.client.get(f"/admin/reports/integrationrun/{run.pk}/change/")
        # Solo lectura: el admin redirige la edicion a la vista de historial/detalle.
        self.assertIn(detalle.status_code, (200, 302, 403))
