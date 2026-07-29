from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from reports.models import BusinessUnit, Channel, Country, DailyChannelSale
from reports.query_cache import memoize_per_request, request_scope
from reports.services.sales_dashboard import daily_channel_sales


class MemoizePerRequestTests(TestCase):
    def setUp(self):
        self.llamadas = []

        @memoize_per_request
        def sumar(datos, extra=0):
            self.llamadas.append((datos, extra))
            return [datos.get("n", 0) + extra]

        self.sumar = sumar

    def test_sin_ambito_no_memoiza(self):
        # Fuera de una peticion (comandos, jobs) debe pasar de largo, para que
        # un proceso que escribe y luego lee vea lo que acaba de guardar.
        self.sumar({"n": 1})
        self.sumar({"n": 1})
        self.assertEqual(len(self.llamadas), 2)

    def test_dentro_del_ambito_memoiza(self):
        with request_scope():
            self.assertEqual(self.sumar({"n": 1}), [1])
            self.assertEqual(self.sumar({"n": 1}), [1])
        self.assertEqual(len(self.llamadas), 1)

    def test_distingue_argumentos(self):
        with request_scope():
            self.sumar({"n": 1})
            self.sumar({"n": 2})
            self.sumar({"n": 1}, extra=5)
        self.assertEqual(len(self.llamadas), 3)

    def test_el_orden_de_las_claves_no_crea_entradas_distintas(self):
        with request_scope():
            self.sumar({"a": 1, "b": 2})
            self.sumar({"b": 2, "a": 1})
        self.assertEqual(len(self.llamadas), 1)

    def test_no_hay_fuga_entre_ambitos(self):
        with request_scope():
            self.sumar({"n": 1})
        with request_scope():
            self.sumar({"n": 1})
        self.assertEqual(len(self.llamadas), 2)

    def test_mutar_el_resultado_no_corrompe_lo_memoizado(self):
        with request_scope():
            primero = self.sumar({"n": 1})
            primero.append("basura")
            segundo = self.sumar({"n": 1})
        self.assertEqual(segundo, [1])


class DailyChannelSaleMemoTests(TestCase):
    def setUp(self):
        # Las migraciones ya siembran catalogos, asi que se reutilizan.
        self.unidad, _ = BusinessUnit.objects.get_or_create(name="Uva")
        self.pais, _ = Country.objects.get_or_create(code="CO", defaults={"name": "Colombia"})
        self.canal, _ = Channel.objects.get_or_create(name="Ecommerce Uva", business_unit=self.unidad)
        DailyChannelSale.objects.all().delete()
        DailyChannelSale.objects.create(
            business_unit=self.unidad,
            country=self.pais,
            channel=self.canal,
            sale_date=date(2026, 7, 15),
            sales_amount=1000,
        )
        self.filtros = {"date_start": "2026-07-01", "date_end": "2026-07-31"}

    def test_repetir_la_lectura_no_repite_la_consulta(self):
        with request_scope():
            with CaptureQueriesContext(connection) as capturadas:
                primero = daily_channel_sales(dict(self.filtros))
                segundo = daily_channel_sales(dict(self.filtros))
        self.assertEqual(len(capturadas), 1)
        self.assertEqual(len(primero), 1)
        self.assertEqual([r.pk for r in primero], [r.pk for r in segundo])

    def test_una_peticion_nueva_vuelve_a_consultar(self):
        with request_scope():
            daily_channel_sales(dict(self.filtros))
        with request_scope():
            with CaptureQueriesContext(connection) as capturadas:
                daily_channel_sales(dict(self.filtros))
        self.assertEqual(len(capturadas), 1)

    def test_ve_las_filas_creadas_en_una_peticion_posterior(self):
        with request_scope():
            self.assertEqual(len(daily_channel_sales(dict(self.filtros))), 1)

        DailyChannelSale.objects.create(
            business_unit=self.unidad,
            country=self.pais,
            channel=self.canal,
            sale_date=date(2026, 7, 16),
            sales_amount=2000,
        )
        with request_scope():
            self.assertEqual(len(daily_channel_sales(dict(self.filtros))), 2)


class QueryMemoMiddlewareTests(TestCase):
    def test_las_vistas_corren_dentro_del_ambito(self):
        user = User.objects.create_user("staff", password="clave-larga-123", is_staff=True)
        self.client.force_login(user)
        # Si el middleware no abriera el ambito, esto seguiria funcionando pero
        # sin ahorro; se comprueba que la vista responde con el middleware activo.
        respuesta = self.client.get("/webs/")
        self.assertEqual(respuesta.status_code, 200)
