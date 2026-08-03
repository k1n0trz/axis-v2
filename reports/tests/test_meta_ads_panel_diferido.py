"""El panel de Meta no debe bloquear el render.

Regresion: /uva/ tardaba 16 s y /uva/comfama/ 17 s con la cache fria, porque el
render se quedaba esperando varias peticiones HTTP encadenadas a Meta. El timeout
configurado era de 8 s por llamada, asi que el techo real era 8 s por el numero de
llamadas.

Ahora la vista solo lee cache; si no hay nada, la pagina sale de inmediato con el
panel en `pending` y el navegador pide el endpoint aparte.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.services.meta_ads_panel import build_uva_meta_ads_preview

FILTROS = {"country": "CO", "date_start": "2026-07-01", "date_end": "2026-07-29"}

ANUNCIO = {
    "id": "123",
    "name": "Anuncio de prueba",
    "created_time": "2026-07-10T10:00:00+0000",
    "effective_status": "ACTIVE",
    "campaign": {"name": "Campana CO"},
    "adset": {"name": "Conjunto CO"},
    "creative": {"title": "Titular", "body": "Cuerpo"},
}


@override_settings(
    META_ACCESS_TOKEN="token-de-prueba",
    META_CO_ACCOUNT_ID="act_1",
    META_ADS_PREVIEW_MAX_IFRAMES=0,
)
class PanelDiferidoTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_sin_cache_no_llama_a_meta_y_marca_pendiente(self):
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)
            cliente.assert_not_called()

        self.assertTrue(preview["pending"])
        self.assertEqual(preview["ads"], [])
        self.assertIn("Preparando", preview["message"])

    def test_con_cache_caliente_devuelve_el_panel_sin_llamar_a_meta(self):
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = [ANUNCIO]
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            build_uva_meta_ads_preview(dict(FILTROS))

        with patch("reports.services.meta_ads_panel.MetaAdsClient") as sin_usar:
            preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)
            sin_usar.assert_not_called()

        self.assertNotIn("pending", preview)
        self.assertEqual(len(preview["ads"]), 1)

    def test_un_fallo_cacheado_no_vuelve_a_quedar_pendiente(self):
        # Importa para no recargar en bucle: tras el fallo la pagina ya no pide
        # el panel otra vez.
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.side_effect = RuntimeError("Meta cayo")
            build_uva_meta_ads_preview(dict(FILTROS))

        preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)

        self.assertNotIn("pending", preview)
        self.assertIn("No fue posible cargar", preview["message"])


@override_settings(
    META_ACCESS_TOKEN="token-de-prueba",
    META_CO_ACCOUNT_ID="act_1",
    META_ADS_PREVIEW_MAX_IFRAMES=0,
)
class EndpointDelPanelTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="analista", password="secreto", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("reports:uva_meta_ads_panel_api")

    def _pedir(self, **extra):
        datos = {"country": "CO", "date_start": "2026-07-01", "date_end": "2026-07-29", **extra}
        return self.client.post(self.url, datos)

    def test_trae_el_panel_y_lo_deja_en_cache(self):
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = [ANUNCIO]
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            respuesta = self._pedir()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"ok": True, "ad_count": 1, "message": ""})
        # Ya en cache: la vista lo encuentra sin permiso para ir a Meta.
        preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)
        self.assertEqual(len(preview["ads"]), 1)

    def test_usa_un_timeout_holgado_porque_nadie_espera_la_pagina(self):
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = []
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            with self.settings(META_ADS_PREVIEW_PANEL_TIMEOUT=60):
                self._pedir()

        self.assertEqual(cliente.call_args.kwargs["timeout"], 60)

    def test_el_alcance_comfama_pide_su_propio_panel(self):
        # El alcance "only" deja pasar solo campanas Comfama, asi que el anuncio
        # de prueba tiene que serlo.
        anuncio_comfama = {**ANUNCIO, "campaign": {"name": "Comfama WhatsApp CO"}}
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = [anuncio_comfama]
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            self._pedir(comfama_scope="only")

        # El panel Comfama y el general viven en claves de cache distintas.
        general = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)
        comfama = build_uva_meta_ads_preview(dict(FILTROS), comfama_scope="only", allow_live_fetch=False)
        self.assertTrue(general.get("pending"))
        self.assertEqual(len(comfama["ads"]), 1)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_exige_sesion_de_staff(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {"country": "CO"})
        self.assertIn(respuesta.status_code, (302, 403))


@override_settings(
    META_ACCESS_TOKEN="token-de-prueba",
    META_CO_ACCOUNT_ID="act_1",
    META_ADS_PREVIEW_MAX_IFRAMES=0,
)
class SinBucleDeRecargaTests(TestCase):
    """El bloque de espera tiene que pedir el MISMO rango que la vista va a leer.

    Bug reportado en produccion: /uva/ se recargaba en bucle infinito. Las fechas del
    bloque salian de `filters`, que **no existe** en el contexto de /uva/, asi que
    llegaban vacias; el endpoint caia a `hoy`, cacheaba esa clave, la vista seguia sin
    encontrar la suya y el JS recargaba otra vez. Para siempre.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="analista", password="secreto", is_staff=True)
        self.client.force_login(self.user)

    def test_el_payload_pendiente_trae_el_rango_pedido(self):
        preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)

        self.assertTrue(preview["pending"])
        self.assertEqual(preview["date_start"], FILTROS["date_start"])
        self.assertEqual(preview["date_end"], FILTROS["date_end"])

    def test_la_plantilla_lee_las_fechas_del_preview_y_no_del_contexto(self):
        """El contrato de la plantilla, que es donde estuvo el bug.

        Se renderiza el include con `filters` **ausente** a proposito: asi era el
        contexto de /uva/. Si la plantilla volviera a leer `filters.date_start`, los
        atributos saldrian vacios y el bucle regresaria.
        """
        from django.template.loader import render_to_string

        preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)
        html = render_to_string(
            "reports/includes/meta_ads_pending.html",
            {"preview": preview, "comfama_scope": "exclude"},
        )

        self.assertIn('data-meta-panel-date-start="2026-07-01"', html)
        self.assertIn('data-meta-panel-date-end="2026-07-29"', html)
        self.assertIn('data-meta-panel-country="CO"', html)
        # Lo que causaba el bucle: los atributos vacios.
        self.assertNotIn('data-meta-panel-date-start=""', html)
        self.assertNotIn('data-meta-panel-date-end=""', html)

    def test_tras_pedir_el_panel_la_vista_ya_no_queda_pendiente(self):
        """El ciclo completo: pendiente -> endpoint -> la vista lo encuentra en cache.

        Si las claves de cache no coinciden, este test falla y el bucle vuelve.
        """
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = [ANUNCIO]
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            respuesta = self.client.post(
                reverse("reports:uva_meta_ads_panel_api"),
                {"country": "CO", "date_start": FILTROS["date_start"], "date_end": FILTROS["date_end"]},
            )
        self.assertTrue(respuesta.json()["ok"])

        # La vista, sin permiso para ir a Meta, ahora si lo encuentra.
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as sin_usar:
            preview = build_uva_meta_ads_preview(dict(FILTROS), allow_live_fetch=False)
            sin_usar.assert_not_called()
        self.assertNotIn("pending", preview)
        self.assertEqual(len(preview["ads"]), 1)

    def test_el_bloque_no_reintenta_sin_rango(self):
        # Guardia en el JS: sin fechas no se pide nada, para no cachear otra clave.
        from pathlib import Path

        js = Path("reports/templates/reports/includes/meta_ads_pending.html").read_text(encoding="utf-8")
        self.assertIn("if (!desde || !hasta)", js)
        self.assertIn("sessionStorage", js)
