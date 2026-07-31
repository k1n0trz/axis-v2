"""Abrir una pagina no debe escribir en la base.

Regresion: /bali/, /marketplace/, /ad-spend/, /web-sales/ y /webs/ llamaban a
`ensure_*_catalogs()` o `seed_websites()` dentro del render. Como esas funciones
usan `update_or_create`, cada GET hacia entre 4 y 10 escrituras y hasta 6
transacciones contra Cloud SQL, reescribia `updated_at` de unidades y canales con
cada visita, y hacia imposible servir la app desde una replica de lectura.

Medido antes y despues:

    /bali/          45 consultas, 7 escrituras  ->  20 consultas, 0
    /marketplace/   40 consultas, 9 escrituras  ->  18 consultas, 0
    /ad-spend/      43 consultas, 10 escrituras ->  18 consultas, 0
    /web-sales/     34 consultas, 8 escrituras  ->  16 consultas, 0
    /webs/          24 consultas, 4 escrituras  ->   6 consultas, 0
"""
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from reports.services.sales_dashboard import (
    ensure_ad_platform_catalogs,
    ensure_bali_catalogs,
    ensure_marketplace_catalogs,
    ensure_uva_catalogs,
)
from reports.services.website_monitor import seed_websites

RUTAS = [
    "/",
    "/uva/",
    "/bali/",
    "/marketplace/",
    "/ad-spend/",
    "/web-sales/",
    "/webs/",
    "/excel/",
    "/operation/",
]


class GetSinEscriturasTests(TestCase):
    def setUp(self):
        # Sembrar aqui si: en una prueba escribir es correcto. El punto es que la
        # vista no lo haga.
        ensure_uva_catalogs()
        ensure_bali_catalogs()
        ensure_marketplace_catalogs()
        ensure_ad_platform_catalogs()
        seed_websites()
        self.user = User.objects.create_user(username="analista", password="secreto", is_staff=True)
        self.client.force_login(self.user)

    def test_ninguna_pagina_escribe_al_abrirla(self):
        for ruta in RUTAS:
            with self.subTest(ruta=ruta):
                with CaptureQueriesContext(connection) as consultas:
                    respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200)
                escrituras = [
                    consulta["sql"]
                    for consulta in consultas.captured_queries
                    # La cache de Django vive en una tabla; esas escrituras son
                    # del backend de cache, no del render.
                    if consulta["sql"].upper().lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
                    and "axis_cache" not in consulta["sql"]
                ]
                self.assertEqual(escrituras, [], f"{ruta} escribio: {escrituras}")
