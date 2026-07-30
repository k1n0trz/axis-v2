"""Monitoreo de webs: siembra, escrituras en GET y visibilidad de producto.

Regresiones cubiertas:

- `seed_websites` usaba `update_or_create`, asi que revertia cualquier edicion
  hecha en el admin en la siguiente corrida.
- `/webs/` sembraba en cada GET: 4 escrituras por carga de pagina.
- `_product_visibility` existia pero nadie la llamaba, asi que los contadores de
  producto quedaban siempre en "unknown".
- El respaldo al origen hacia que una web en subcarpeta (copauva.com/ec/)
  reportara el catalogo de la tienda raiz como si fuera propio.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from reports import views
from reports.models import Website, WebsiteHealthCheck
from reports.services import website_monitor
from reports.services.website_monitor import scan_website, seed_websites


class RespuestaFalsa:
    """Lo minimo de `requests.Response` que usa el monitor."""

    def __init__(self, url, payload=None, text="", status_code=200, headers=None):
        self.url = url
        self._payload = payload
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.history = []

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        if self._payload is None:
            raise ValueError("sin json")
        return self._payload


class SiembraDeWebsTests(TestCase):
    def test_no_sobrescribe_lo_editado_en_el_admin(self):
        seed_websites()
        web = Website.objects.get(slug="copa-uva-mexico")
        Website.objects.filter(pk=web.pk).update(
            url="https://uvawomen.mx/tienda/",
            monitor_enabled=False,
            notes="editado por el equipo",
        )

        seed_websites()

        web.refresh_from_db()
        self.assertEqual(web.url, "https://uvawomen.mx/tienda/")
        self.assertFalse(web.monitor_enabled)
        self.assertEqual(web.notes, "editado por el equipo")

    def test_crea_las_que_falten(self):
        Website.objects.all().delete()

        webs = seed_websites()

        self.assertEqual(len(webs), 4)
        self.assertEqual(Website.objects.count(), 4)


class WebsGetSinEscriturasTests(TestCase):
    def setUp(self):
        seed_websites()
        self.user = User.objects.create_user(username="analista", password="secreto", is_staff=True)
        self.client.force_login(self.user)

    def test_abrir_la_pagina_no_escribe_en_la_base(self):
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get("/webs/")

        self.assertEqual(respuesta.status_code, 200)
        escrituras = [
            consulta["sql"]
            for consulta in consultas.captured_queries
            if consulta["sql"].upper().lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
            and "axis_cache" not in consulta["sql"]
        ]
        self.assertEqual(escrituras, [])


class EtiquetaDeCatalogoTests(TestCase):
    """"No se pudo leer" y "leimos y hay cero" no deben verse iguales."""

    def _etiqueta(self, **campos):
        return views._website_products_summary(WebsiteHealthCheck(**campos))

    def test_distingue_cada_estado(self):
        casos = [
            ({"products_visible_status": "ok", "products_in_stock_count": 20, "products_out_of_stock_count": 0}, "20 en stock", "green"),
            ({"products_visible_status": "ok", "products_in_stock_count": 18, "products_out_of_stock_count": 2}, "18 en stock, 2 agotados", "yellow"),
            ({"products_visible_status": "empty"}, "La tienda no devolvio productos", "red"),
            ({"products_visible_status": "blocked"}, "La tienda no permitio leer el catalogo", "yellow"),
            ({"products_visible_status": "not_configured"}, "Sin lectura de catalogo para esta plataforma", "muted"),
            ({"products_visible_status": "unknown"}, "Sin dato", "muted"),
        ]
        for campos, etiqueta, clase in casos:
            with self.subTest(estado=campos["products_visible_status"]):
                self.assertEqual(self._etiqueta(**campos), (etiqueta, clase))

    def test_sin_chequeo_no_revienta(self):
        self.assertEqual(views._website_products_summary(None), ("Sin dato", "muted"))


class VisibilidadDeProductoTests(TestCase):
    def setUp(self):
        seed_websites()

    def _escanear(self, web, productos_json, url_productos, pagespeed=None):
        pagina = RespuestaFalsa(web.url, text="<title>Tienda</title> wp-content", headers={})

        def falso_get(url, **kwargs):
            if url == url_productos:
                return RespuestaFalsa(url, payload=productos_json)
            if url.startswith(web.url) or url == web.url:
                return pagina
            return RespuestaFalsa(url, status_code=404)

        with patch.object(website_monitor.requests, "get", side_effect=falso_get), patch.object(
            website_monitor, "_pagespeed_metrics", return_value=pagespeed or {"pagespeed_status": "ok"}
        ), patch.object(website_monitor, "_ssl_status", return_value={"ssl_valid": True}):
            return scan_website(web)

    def test_el_escaneo_llena_los_contadores_de_producto(self):
        web = Website.objects.get(slug="copa-uva-colombia")
        productos = [
            {"name": "Copa Uva A", "is_in_stock": True},
            {"name": "Copa Uva B", "is_in_stock": True},
            {"name": "Disco", "is_in_stock": False},
        ]

        chequeo = self._escanear(web, productos, f"{web.url}{website_monitor.STORE_API_PATH}")

        self.assertEqual(chequeo.products_visible_status, "ok")
        self.assertEqual(chequeo.products_visible_count, 3)
        self.assertEqual(chequeo.products_in_stock_count, 2)
        self.assertEqual(chequeo.products_out_of_stock_count, 1)

    def test_una_web_en_subcarpeta_no_consulta_el_origen(self):
        consultadas = []

        def registrar(url, **kwargs):
            consultadas.append(url)
            return RespuestaFalsa(url, status_code=500)

        with patch.object(website_monitor.requests, "get", side_effect=registrar):
            resultado = website_monitor._wordpress_products("https://copauva.com/ec/", "")

        self.assertEqual(consultadas, [f"https://copauva.com/ec/{website_monitor.STORE_API_PATH}"])
        self.assertEqual(resultado["products_visible_status"], "blocked")

    def test_una_web_en_la_raiz_si_consulta_el_origen(self):
        consultadas = []

        def registrar(url, **kwargs):
            consultadas.append(url)
            return RespuestaFalsa(url, payload=[{"name": "Copa", "is_in_stock": True}])

        with patch.object(website_monitor.requests, "get", side_effect=registrar):
            resultado = website_monitor._wordpress_products("https://copauva.com/", "")

        self.assertEqual(consultadas, [f"https://copauva.com/{website_monitor.STORE_API_PATH}"])
        self.assertEqual(resultado["products_visible_count"], 1)

    def test_un_fallo_de_pagespeed_no_borra_los_puntajes_buenos(self):
        web = Website.objects.get(slug="copa-uva-colombia")
        buenos = {
            "pagespeed_status": "ok",
            "performance_score": 46,
            "accessibility_score": 80,
            "best_practices_score": 96,
            "seo_score": 100,
        }
        url_productos = f"{web.url}{website_monitor.STORE_API_PATH}"
        productos = [{"name": "Copa", "is_in_stock": True}]
        primero = self._escanear(web, productos, url_productos, pagespeed=buenos)
        self.assertEqual(primero.performance_score, 46)

        fallo = {"pagespeed_status": "error", "raw_pagespeed_probe": {"error": "Read timed out"}}
        segundo = self._escanear(web, productos, url_productos, pagespeed=fallo)

        self.assertEqual(segundo.pagespeed_status, "stale")
        self.assertEqual(segundo.performance_score, 46)
        self.assertEqual(segundo.accessibility_score, 80)
        self.assertEqual(segundo.seo_score, 100)
        self.assertIn("carried_over_from", segundo.raw_payload["pagespeed_probe"])

    def test_sin_medicion_previa_el_fallo_queda_como_fallo(self):
        web = Website.objects.get(slug="copa-uva-colombia")
        fallo = {"pagespeed_status": "error", "raw_pagespeed_probe": {"error": "Read timed out"}}

        chequeo = self._escanear(web, [], f"{web.url}{website_monitor.STORE_API_PATH}", pagespeed=fallo)

        self.assertEqual(chequeo.pagespeed_status, "error")
        self.assertIsNone(chequeo.performance_score)

    def test_bali_usa_la_admin_api_de_shopify(self):
        web = Website.objects.get(slug="bali-sex-store-colombia")
        productos = {"products": [
            {"title": "Bala vibradora", "variants": [{"inventory_quantity": 696}]},
            {"title": "Accesorio", "variants": [{"inventory_quantity": 0}]},
        ]}
        llamadas = []

        def falso_get(url, **kwargs):
            llamadas.append(url)
            return RespuestaFalsa(url, payload=productos)

        with self.settings(
            SHOPIFY_BALI_SHOP_DOMAIN="bali.myshopify.com",
            SHOPIFY_BALI_ACCESS_TOKEN="token",
            SHOPIFY_BALI_API_VERSION="2025-10",
        ), patch.object(website_monitor.requests, "get", side_effect=falso_get):
            resultado = website_monitor._product_visibility(web, web.url)

        self.assertEqual(resultado["raw_product_probe"]["source"], "shopify-admin-api")
        self.assertEqual(resultado["products_visible_count"], 2)
        self.assertEqual(resultado["products_in_stock_count"], 1)
        self.assertEqual(resultado["products_out_of_stock_count"], 1)
        self.assertEqual(llamadas, ["https://bali.myshopify.com/admin/api/2025-10/products.json"])

    def test_sin_token_de_shopify_cae_al_escaparate_publico(self):
        web = Website.objects.get(slug="bali-sex-store-colombia")
        llamadas = []

        def falso_get(url, **kwargs):
            llamadas.append(url)
            return RespuestaFalsa(url, payload=[{"title": "Bala", "variants": [{"inventory_quantity": 3}]}])

        with self.settings(SHOPIFY_BALI_ACCESS_TOKEN=""), patch.object(
            website_monitor.requests, "get", side_effect=falso_get
        ):
            resultado = website_monitor._product_visibility(web, web.url)

        self.assertEqual(resultado["raw_product_probe"]["source"], "shopify-products-json")
        self.assertEqual(llamadas, ["https://balisexstore.com/products.json?limit=20"])

    def test_una_url_vacia_no_deja_chequeo_a_medias(self):
        web = Website.objects.get(slug="copa-uva-mexico")
        Website.objects.filter(pk=web.pk).update(url="")
        web.refresh_from_db()

        chequeo = scan_website(web)

        self.assertEqual(chequeo.overall_status, WebsiteHealthCheck.OverallStatus.UNKNOWN)
        self.assertEqual(chequeo.error_message, "URL pendiente.")
