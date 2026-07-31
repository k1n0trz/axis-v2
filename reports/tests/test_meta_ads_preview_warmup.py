from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from reports.services.meta_ads_panel import build_uva_meta_ads_preview

FILTERS = {"country": "CO", "date_start": "2026-07-01", "date_end": "2026-07-29"}

FAKE_AD = {
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
    META_MX_ACCOUNT_ID="",
    META_EC_ACCOUNT_ID="",
    META_ADS_PREVIEW_MAX_IFRAMES=0,
)
class MetaAdsPreviewCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def _client(self, ads=None, fail=False):
        """Devuelve un patch de MetaAdsClient con el comportamiento pedido."""
        patcher = patch("reports.services.meta_ads_panel.MetaAdsClient")
        client_cls = patcher.start()
        self.addCleanup(patcher.stop)
        client = client_cls.return_value
        if fail:
            client.get_active_ads.side_effect = RuntimeError("Meta no responde")
        else:
            client.get_active_ads.return_value = ads if ads is not None else [FAKE_AD]
        client.get_ad_images_by_hashes.return_value = {}
        return client

    def test_usa_la_cache_en_la_segunda_llamada(self):
        client = self._client()
        build_uva_meta_ads_preview(dict(FILTERS))
        build_uva_meta_ads_preview(dict(FILTERS))
        self.assertEqual(client.get_active_ads.call_count, 1)

    def test_force_refresh_ignora_la_cache(self):
        client = self._client()
        build_uva_meta_ads_preview(dict(FILTERS))
        build_uva_meta_ads_preview(dict(FILTERS), force_refresh=True)
        self.assertEqual(client.get_active_ads.call_count, 2)

    def test_force_refresh_usa_el_timeout_indicado(self):
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as client_cls:
            client_cls.return_value.get_active_ads.return_value = [FAKE_AD]
            client_cls.return_value.get_ad_images_by_hashes.return_value = {}
            build_uva_meta_ads_preview(dict(FILTERS), force_refresh=True, timeout=90)
        self.assertEqual(client_cls.call_args.kwargs["timeout"], 90)

    def test_un_fallo_se_cachea_para_no_repetir_el_camino_lento(self):
        client = self._client(fail=True)
        primera = build_uva_meta_ads_preview(dict(FILTERS))
        segunda = build_uva_meta_ads_preview(dict(FILTERS))
        self.assertIn("No fue posible cargar anuncios", primera["message"])
        self.assertEqual(segunda["message"], primera["message"])
        self.assertEqual(client.get_active_ads.call_count, 1)

    def test_un_precalentamiento_fallido_no_borra_el_panel_bueno(self):
        # Primero se cachea un panel valido.
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as ok_cls:
            ok_cls.return_value.get_active_ads.return_value = [FAKE_AD]
            ok_cls.return_value.get_ad_images_by_hashes.return_value = {}
            build_uva_meta_ads_preview(dict(FILTERS))

        # Luego un precalentamiento falla: el panel bueno debe sobrevivir.
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as bad_cls:
            bad_cls.return_value.get_active_ads.side_effect = RuntimeError("Meta cayo")
            build_uva_meta_ads_preview(dict(FILTERS), force_refresh=True, timeout=90)

        with patch("reports.services.meta_ads_panel.MetaAdsClient") as unused_cls:
            despues = build_uva_meta_ads_preview(dict(FILTERS))
            unused_cls.assert_not_called()
        self.assertEqual(len(despues["ads"]), 1)


@override_settings(
    META_ACCESS_TOKEN="token-de-prueba",
    META_CO_ACCOUNT_ID="act_1",
    META_MX_ACCOUNT_ID="",
    META_EC_ACCOUNT_ID="",
    META_ADS_PREVIEW_MAX_IFRAMES=0,
)
class WarmMetaAdsPreviewCommandTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_precalienta_solo_los_paises_configurados(self):
        salida = StringIO()
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as client_cls:
            client_cls.return_value.get_active_ads.return_value = [FAKE_AD]
            client_cls.return_value.get_ad_images_by_hashes.return_value = {}
            call_command("warm_meta_ads_preview", "--timeout=30", stdout=salida)
        texto = salida.getvalue()
        # CO tiene cuenta (dos alcances); MX y EC no, y deben omitirse sin fallar.
        self.assertIn("CO/exclude: 1 anuncios en cache.", texto)
        self.assertIn("CO/only", texto)
        self.assertIn("MX/exclude: sin cuenta Meta configurada", texto)
        self.assertIn("EC/exclude: sin cuenta Meta configurada", texto)

    def test_deja_el_panel_listo_en_cache(self):
        # El rango se pasa explicito: sin esto el comando lo derivaba de la
        # fecha de hoy y la prueba solo pasaba el dia que coincidia con FILTERS.
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as client_cls:
            client_cls.return_value.get_active_ads.return_value = [FAKE_AD]
            client_cls.return_value.get_ad_images_by_hashes.return_value = {}
            call_command(
                "warm_meta_ads_preview",
                "--timeout=30",
                f"--date-start={FILTERS['date_start']}",
                f"--date-end={FILTERS['date_end']}",
                stdout=StringIO(),
            )

        # Tras precalentar, la vista no debe volver a llamar a Meta.
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as unused_cls:
            preview = build_uva_meta_ads_preview(dict(FILTERS))
            unused_cls.assert_not_called()
        self.assertEqual(len(preview["ads"]), 1)

    def test_acepta_rango_de_fechas_explicito(self):
        salida = StringIO()
        with patch("reports.services.meta_ads_panel.MetaAdsClient") as client_cls:
            client_cls.return_value.get_active_ads.return_value = []
            client_cls.return_value.get_ad_images_by_hashes.return_value = {}
            call_command(
                "warm_meta_ads_preview",
                "--date-start=2026-06-01",
                "--date-end=2026-06-30",
                "--country=CO",
                stdout=salida,
            )
        self.assertIn("2026-06-01 al 2026-06-30", salida.getvalue())
