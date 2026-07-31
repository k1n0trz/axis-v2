"""Las metricas de los anuncios de Meta no deben perderse en silencio.

Sintoma reportado: en el panel, ordenar por "Mas compras" no cambiaba nada. La
causa no era el orden: los 31 anuncios traian inversion, ROAS y compras en cero, y
ordenar por un campo que vale cero en todas las filas no cambia nada.

La causa real: Meta responde HTTP 500 "Please reduce the amount of data you're
asking for" sobre la peticion que trae los insights, de forma **intermitente**. El
cliente reintentaba sin insights **con el mismo tamano de pagina**, esa peticion
pasaba, y el panel se quedaba con todo en cero sin decir nada. Unos dias el panel
funcionaba y otros no.

Verificado contra la API real: con la correccion, los 31 anuncios traen inversion y
16 traen compras; el mayor gasta 2.905.869 COP con 133 compras y ROAS 5,12.
"""
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from reports.integrations.clients import MetaAdsClient
from reports.services.meta_ads_panel import build_uva_meta_ads_preview

ANUNCIO_BASE = {
    "id": "1",
    "name": "Anuncio con datos",
    "created_time": "2026-07-10T10:00:00+0000",
    "effective_status": "ACTIVE",
    "campaign": {"name": "Campana CO"},
    "adset": {"name": "Conjunto CO"},
    "creative": {"title": "Titular", "body": "Cuerpo"},
}
INSIGHTS = {
    "data": [
        {
            "spend": "2905869",
            "impressions": "100000",
            "reach": "80000",
            "clicks": "1500",
            "actions": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "133"}],
            "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "14878049"}],
            "purchase_roas": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "5.12"}],
        }
    ]
}


class ReduccionDePaginaTests(TestCase):
    """Ante "reduce the amount of data", se baja el tamano de pagina, no los insights."""

    def _cliente_que_falla_en_paginas_grandes(self, limite_maximo):
        intentos = []

        def falso_get(self, url, params=None, action=""):
            fields = (params or {}).get("fields", "")
            limit = (params or {}).get("limit")
            intentos.append({"insights": "insights" in fields, "limit": limit})
            if "insights" in fields and limit and limit > limite_maximo:
                raise RuntimeError("Meta Ads devolvio HTTP 500. Detalle: Please reduce the amount of data you're asking for")
            anuncio = dict(ANUNCIO_BASE)
            if "insights" in fields:
                anuncio["insights"] = INSIGHTS
            return {"data": [anuncio]}

        return falso_get, intentos

    def test_reintenta_con_paginas_mas_pequenas_antes_de_rendirse(self):
        falso_get, intentos = self._cliente_que_falla_en_paginas_grandes(limite_maximo=25)
        from datetime import date

        with patch.object(MetaAdsClient, "_get_meta_json", falso_get):
            cliente = MetaAdsClient("token")
            filas = cliente.get_active_ads("act_1", date_start=date(2026, 7, 1), date_end=date(2026, 7, 31), max_records=1)

        # La primera peticion falla por tamano; la siguiente insiste con insights.
        self.assertTrue(intentos[0]["insights"])
        self.assertTrue(intentos[1]["insights"])
        self.assertLess(intentos[1]["limit"], intentos[0]["limit"])
        # Y termina trayendo los insights, que es el punto.
        self.assertTrue(filas[0].get("insights"))

    def test_si_ninguna_pagina_sirve_todavia_devuelve_los_anuncios(self):
        # Perder las metricas es malo; perder el panel entero es peor.
        falso_get, intentos = self._cliente_que_falla_en_paginas_grandes(limite_maximo=0)
        from datetime import date

        with patch.object(MetaAdsClient, "_get_meta_json", falso_get):
            cliente = MetaAdsClient("token")
            filas = cliente.get_active_ads("act_1", date_start=date(2026, 7, 1), date_end=date(2026, 7, 31), max_records=1)

        self.assertEqual(len(filas), 1)
        self.assertNotIn("insights", filas[0])
        self.assertTrue(any(not i["insights"] for i in intentos))


@override_settings(
    META_ACCESS_TOKEN="token-de-prueba",
    META_CO_ACCOUNT_ID="act_1",
    META_ADS_PREVIEW_MAX_IFRAMES=0,
)
class AvisoDeMetricasFaltantesTests(TestCase):
    FILTROS = {"country": "CO", "date_start": "2026-07-01", "date_end": "2026-07-31"}

    def setUp(self):
        cache.clear()

    def _preview(self, con_insights):
        anuncio = dict(ANUNCIO_BASE)
        if con_insights:
            anuncio["insights"] = INSIGHTS
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = [anuncio]
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            return build_uva_meta_ads_preview(dict(self.FILTROS))

    def test_con_metricas_no_hay_aviso_y_los_numeros_llegan(self):
        preview = self._preview(con_insights=True)

        self.assertFalse(preview["metrics_unavailable"])
        metricas = preview["ads"][0]["metrics"]
        self.assertEqual(metricas["spend"], 2905869.0)
        self.assertEqual(metricas["purchases"], 133)
        self.assertEqual(metricas["roas"], 5.12)

    def test_sin_metricas_el_panel_lo_avisa(self):
        # Antes se veia igual que un panel sano, con todo en cero.
        preview = self._preview(con_insights=False)

        self.assertTrue(preview["metrics_unavailable"])
        self.assertEqual(preview["ads"][0]["metrics"]["spend"], 0.0)
        self.assertEqual(preview["ads"][0]["metrics"]["purchases"], 0)

    def test_un_panel_vacio_no_se_marca_como_metricas_faltantes(self):
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as cliente:
            cliente.return_value.get_active_ads.return_value = []
            cliente.return_value.get_ad_images_by_hashes.return_value = {}
            preview = build_uva_meta_ads_preview(dict(self.FILTROS))

        self.assertFalse(preview["metrics_unavailable"])
        self.assertIn("No se encontraron anuncios", preview["message"])
