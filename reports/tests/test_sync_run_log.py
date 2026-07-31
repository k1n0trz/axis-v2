"""El orquestador diario deja una fila de bitacora por fuente.

Se instrumento el orquestador y no cada comando: es un solo punto y cubre
exactamente lo que corre desatendido. Un comando lanzado a mano no queda
registrado, y eso esta bien: el problema que resuelve la bitacora es no saber que
paso mientras nadie miraba.

Antes, la salida de cada comando se capturaba y se **descartaba** cuando terminaba
bien; solo sobrevivia el mensaje de error si fallaba. Ahora el resumen se guarda.
"""
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from reports.management.commands.sync_axis_daily_data import Command
from reports.models import IntegrationRun


class FuenteYFechaTests(TestCase):
    def setUp(self):
        self.command = Command()

    def test_la_fecha_del_nombre_no_entra_en_la_fuente(self):
        # Si entrara, cada dia crearia una fuente distinta y `last_run_by_source`
        # no serviria para nada.
        fuente, fecha = self.command._source_and_date(
            {"name": "OneDrive Ecuador 2026-07-30", "command": ["fetch_onedrive_excel"]}
        )
        self.assertEqual(fuente, "onedrive_ecuador")
        self.assertEqual(fecha, date(2026, 7, 30))

    def test_la_fecha_sale_del_comando_cuando_no_esta_en_el_nombre(self):
        casos = [
            (["fetch_woocommerce_sales", "--date", "2026-07-29"], date(2026, 7, 29)),
            (["fetch_google_ads", "--date=2026-07-28"], date(2026, 7, 28)),
            (["fetch_onedrive_excel", "--date-from=2026-07-01", "--date-to=2026-07-31"], date(2026, 7, 31)),
        ]
        for comando, esperada in casos:
            with self.subTest(comando=comando):
                _, fecha = self.command._source_and_date({"name": "Fuente", "command": comando})
                self.assertEqual(fecha, esperada)

    def test_una_fuente_sin_fecha_queda_sin_fecha(self):
        fuente, fecha = self.command._source_and_date(
            {"name": "Mercado Libre Marketplace", "command": ["sync_mercadolibre_marketplace"]}
        )
        self.assertEqual(fuente, "mercado_libre_marketplace")
        self.assertIsNone(fecha)


class ResumenDelPayloadTests(TestCase):
    def setUp(self):
        self.command = Command()

    def test_recorta_las_listas_a_conteos(self):
        # El payload es para diagnosticar: 392 categorias no caben ni sirven.
        payload = self.command._run_payload('{"channel_sale": {"sales_amount": "105967985", "order_count": 80}, "category_sales": [1, 2, 3]}')

        self.assertEqual(payload["category_sales_count"], 3)
        self.assertEqual(payload["channel_sale_amount"], "105967985")
        self.assertEqual(payload["channel_sale_orders"], 80)
        self.assertNotIn("category_sales", payload)

    def test_las_filas_sospechosas_sobreviven_al_recorte(self):
        salida = '{"suspicious_unit_prices": [{"message": "2026-05-24 disco menstrual uva: VALOR 53.94 con CANTIDAD 2..."}]}'

        payload = self.command._run_payload(salida)
        resumen = self.command._run_summary("OneDrive Ecuador", payload)

        self.assertEqual(len(payload["suspicious_unit_prices"]), 1)
        self.assertIn("VALOR sospechoso en 1 filas", resumen)

    def test_una_salida_que_no_es_json_se_guarda_como_texto(self):
        payload = self.command._run_payload("Importacion Ecuador completada. Ventas creadas: 3.")

        self.assertIn("Ventas creadas: 3", payload["output"])

    def test_un_comando_sin_novedades_lo_dice(self):
        self.assertIn("sin novedades", self.command._run_summary("Falabella", {}))


class BitacoraDelSyncTests(TestCase):
    """Corre el orquestador de verdad, con los comandos reemplazados por mocks."""

    def _correr(self, side_effect=None):
        salida = StringIO()
        with patch("reports.management.commands.sync_axis_daily_data.call_command") as llamada:
            if side_effect:
                llamada.side_effect = side_effect
            else:
                llamada.side_effect = lambda *a, **kw: kw["stdout"].write('{"checked": 2}')
            call_command("sync_axis_daily_data", "--date=2026-07-30", "--continue-on-error", stdout=salida)
        return salida.getvalue()

    def test_cada_fuente_deja_su_fila(self):
        self._correr()

        runs = IntegrationRun.objects.all()
        self.assertGreater(runs.count(), 0)
        self.assertTrue(all(r.status == IntegrationRun.Status.SUCCESS for r in runs))
        # La fuente es un slug estable, no el nombre con fecha.
        self.assertTrue(all(" " not in r.source for r in runs))
        self.assertTrue(all(r.summary for r in runs))

    def test_una_fuente_que_falla_queda_marcada_y_las_demas_siguen(self):
        llamadas = {"n": 0}

        def falla_la_primera(*args, **kwargs):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise RuntimeError("la fuente no respondio")
            kwargs["stdout"].write('{"checked": 1}')

        self._correr(side_effect=falla_la_primera)

        fallidas = IntegrationRun.objects.filter(status=IntegrationRun.Status.FAILED)
        exitosas = IntegrationRun.objects.filter(status=IntegrationRun.Status.SUCCESS)
        self.assertEqual(fallidas.count(), 1)
        self.assertIn("la fuente no respondio", fallidas.first().error_message)
        # --continue-on-error: el resto del dia se sigue importando.
        self.assertGreater(exitosas.count(), 0)

    def test_un_dry_run_no_escribe_bitacora(self):
        salida = StringIO()
        call_command("sync_axis_daily_data", "--date=2026-07-30", "--dry-run", stdout=salida)

        self.assertEqual(IntegrationRun.objects.count(), 0)


class DistrisexEnElSyncDiarioTests(TestCase):
    """DistriSex tiene que entrar al sync diario, no solo a corridas manuales.

    Antes de esto el orquestador no la mencionaba: sus ventas y su inversion solo
    existian si alguien corria los comandos a mano.
    """

    def _tareas(self, **settings_extra):
        from django.test import override_settings

        base = {
            "WOOCOMMERCE_DISTRISEX_BASE_URL": "https://distrisexcolombia.com",
            "GOOGLE_ADS_DISTRISEX_CUSTOMER_ID": "9891336542",
        }
        base.update(settings_extra)
        with override_settings(**base):
            return Command()._build_tasks_for_dates(
                [date(2026, 7, 30)],
                {"meta_rules": "m.json", "google_rules": "g.json", "onedrive_sales_lookback_days": 1},
            )

    def _nombres(self, tareas):
        return [t["name"] for t in tareas]

    def test_las_ventas_de_distrisex_entran_al_sync(self):
        tareas = self._tareas()

        self.assertIn("WooCommerce DistriSex", self._nombres(tareas))
        comando = next(t["command"] for t in tareas if t["name"] == "WooCommerce DistriSex")
        self.assertIn("--store", comando)
        self.assertIn("DISTRISEX", comando)
        # Sin mapa de categorias, el catalogo mayorista generaria cientos de
        # categorias basura por dia.
        self.assertIn("--skip-category-sales", comando)

    def test_la_pauta_de_distrisex_no_depende_del_workbook_de_onedrive(self):
        # Uva y Bali se apagan cuando hay workbook; DistriSex no puede, porque ese
        # archivo no incluye su cuenta.
        tareas = self._tareas(ONEDRIVE_GOOGLE_ADS_FILE_PATH="axis/google-ads.xlsx")
        nombres = self._nombres(tareas)

        self.assertIn("Google Ads DistriSex", nombres)
        self.assertNotIn("Google Ads Colombia", nombres)

    def test_sin_credenciales_de_distrisex_no_se_agrega_nada(self):
        tareas = self._tareas(WOOCOMMERCE_DISTRISEX_BASE_URL="", GOOGLE_ADS_DISTRISEX_CUSTOMER_ID="")
        nombres = self._nombres(tareas)

        self.assertNotIn("WooCommerce DistriSex", nombres)
        self.assertNotIn("Google Ads DistriSex", nombres)

    def test_el_slug_de_una_fuente_con_rango_de_fechas_no_incluye_las_fechas(self):
        # "OneDrive Ecuador 2026-07-28..2026-07-30" creaba una fuente distinta cada
        # dia y volvia inutil el historial por fuente.
        fuente, fecha = Command()._source_and_date(
            {"name": "OneDrive Ecuador 2026-07-28..2026-07-30", "command": ["fetch_onedrive_excel"]}
        )
        self.assertEqual(fuente, "onedrive_ecuador")
        self.assertEqual(fecha, date(2026, 7, 30))


class GoogleAdsSiemprePorApiTests(TestCase):
    """Google Ads entra por API, nunca por Excel.

    Las cuatro tareas de Google Ads se apagaban si existia
    ONEDRIVE_GOOGLE_ADS_FILE_PATH. En produccion esa variable apuntaba a
    axis/google-ads.xlsx, un archivo que **no existe**: OneDrive responde 404. Con la
    condicion puesta, la pauta de Google de Uva y Bali no entraba por ningun lado y la
    tarea del workbook fallaba todos los dias.

    En Excel solo hay ventas por WhatsApp (Uva Ecuador, Uva Colombia y Comfama).
    """

    def _nombres(self, **extra):
        from django.test import override_settings

        base = {
            "GOOGLE_ADS_CO_CUSTOMER_ID": "7015245415",
            "GOOGLE_ADS_MX_CUSTOMER_ID": "6143715017",
            "GOOGLE_ADS_EC_CUSTOMER_ID": "6385600284",
            "GOOGLE_ADS_BALI_CUSTOMER_ID": "4042093126",
        }
        base.update(extra)
        with override_settings(**base):
            tareas = Command()._build_tasks_for_dates(
                [date(2026, 7, 30)],
                {"meta_rules": "m.json", "google_rules": "g.json", "onedrive_sales_lookback_days": 1},
            )
        return [t["name"] for t in tareas]

    def test_las_cuatro_cuentas_entran_por_api(self):
        nombres = self._nombres()

        for cuenta in ("Google Ads Colombia", "Google Ads Mexico", "Google Ads Ecuador", "Google Ads Bali"):
            self.assertIn(cuenta, nombres)

    def test_el_workbook_no_apaga_la_api(self):
        # Esta era la regresion: con la variable puesta desaparecian las cuatro.
        nombres = self._nombres(ONEDRIVE_GOOGLE_ADS_FILE_PATH="axis/google-ads.xlsx")

        for cuenta in ("Google Ads Colombia", "Google Ads Mexico", "Google Ads Ecuador", "Google Ads Bali"):
            self.assertIn(cuenta, nombres)

    def test_no_queda_ninguna_tarea_que_lea_google_ads_de_excel(self):
        nombres = self._nombres(ONEDRIVE_GOOGLE_ADS_FILE_PATH="axis/google-ads.xlsx")

        self.assertNotIn("OneDrive Google Ads Workbook", nombres)
