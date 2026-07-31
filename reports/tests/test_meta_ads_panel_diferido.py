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
