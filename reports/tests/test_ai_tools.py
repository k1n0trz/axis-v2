"""Las consultas que la IA hace contra Axis: alcance, permisos y numeros."""
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.ai.tools import TOOL_SPECS, TOOLS, MIN_SPEND_FOR_ROAS, allowed_business_units, run_tool
from reports.models import (
    AdPlatform,
    BusinessUnit,
    Channel,
    Country,
    DailyAdSpend,
    DailyChannelSale,
    UserProfile,
)

HOY = date(2026, 7, 15)


def _staff(username):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    return usuario


class DatosDePruebaMixin:
    def crear_datos(self):
        self.uva, _ = BusinessUnit.objects.get_or_create(name="Uva", defaults={"slug": "uva"})
        self.bali, _ = BusinessUnit.objects.get_or_create(name="Bali", defaults={"slug": "bali"})
        self.co, _ = Country.objects.get_or_create(name="Colombia", defaults={"code": "CO"})
        self.ec, _ = Country.objects.get_or_create(name="Ecuador", defaults={"code": "EC"})
        self.web, _ = Channel.objects.get_or_create(name="Ecommerce Uva", defaults={"slug": "ecommerce-uva"})
        self.meta, _ = AdPlatform.objects.get_or_create(name="Meta Ads", defaults={"slug": "meta-ads"})

        DailyChannelSale.objects.create(
            business_unit=self.uva, country=self.co, channel=self.web, sale_date=HOY,
            sales_amount=Decimal("10000000"), order_count=20, units=40,
        )
        DailyChannelSale.objects.create(
            business_unit=self.bali, country=self.co, channel=self.web, sale_date=HOY,
            sales_amount=Decimal("4000000"), order_count=8, units=10,
        )
        DailyAdSpend.objects.create(
            business_unit=self.uva, country=self.co, ad_platform=self.meta, spend_date=HOY,
            spend_amount=Decimal("2000000"),
        )


class AlcancePorPermisosTests(DatosDePruebaMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.completo = _staff("alejo")
        self.limitado = _staff("solo-bali")
        self.limitado.profile.business_units.set([self.bali])

    def test_sin_marcas_asignadas_ve_todas_las_activas(self):
        nombres = [b.name for b in allowed_business_units(self.completo)]

        self.assertIn("Uva", nombres)
        self.assertIn("Bali", nombres)

    def test_quien_solo_ve_bali_no_recibe_las_ventas_de_uva(self):
        datos = run_tool(
            self.limitado, "get_sales",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "group_by": "business_unit"},
        )

        claves = [f["clave"] for f in datos["desglose"]]
        self.assertEqual(claves, ["Bali"])

    def test_pedir_una_marca_sin_acceso_devuelve_vacio_y_lo_dice(self):
        datos = run_tool(
            self.limitado, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"},
        )

        self.assertEqual(datos["ventas"], 0.0)
        self.assertIn("no tiene acceso", datos["nota"])

    def test_una_marca_que_no_existe_se_distingue_de_una_sin_acceso(self):
        datos = run_tool(
            self.completo, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Inventada"},
        )

        self.assertIn("No hay ninguna marca", datos["nota"])

    def test_las_dimensiones_solo_listan_las_marcas_del_usuario(self):
        datos = run_tool(self.limitado, "list_dimensions", {})

        self.assertEqual(datos["business_units"], ["Bali"])


class NumerosTests(DatosDePruebaMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.user = _staff("alejo")

    def test_el_roas_lo_calcula_axis_no_el_modelo(self):
        datos = run_tool(
            self.user, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"},
        )

        # 10.000.000 / 2.000.000 = 5,0
        self.assertEqual(datos["roas"], 5.0)

    def test_los_importes_vienen_formateados_en_pesos(self):
        datos = run_tool(
            self.user, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"},
        )

        self.assertEqual(datos["ventas_cop"], "10.000.000 COP")
        self.assertIn("COP", datos["inversion_cop"])

    def test_con_inversion_casi_cero_el_roas_es_null_y_explica_por_que(self):
        # Es el caso de DistriSex: vende al mayor casi sin pauta, y el cociente
        # resultante invita a leerlo como rendimiento de pauta cuando no lo es.
        DailyAdSpend.objects.filter(business_unit=self.uva).update(spend_amount=Decimal("500"))

        datos = run_tool(
            self.user, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"},
        )

        self.assertIsNone(datos["roas"])
        self.assertIn("demasiado baja", datos["nota"])

    def test_el_ticket_promedio_sale_de_los_pedidos(self):
        datos = run_tool(
            self.user, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"},
        )

        # 10.000.000 / 20 pedidos
        self.assertEqual(datos["ticket_promedio_cop"], "500.000 COP")

    def test_sin_pedidos_no_inventa_un_ticket(self):
        DailyChannelSale.objects.filter(business_unit=self.uva).update(order_count=0)

        datos = run_tool(
            self.user, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"},
        )

        self.assertIsNone(datos["ticket_promedio_cop"])

    def test_un_periodo_sin_datos_devuelve_ceros_y_no_falla(self):
        datos = run_tool(
            self.user, "get_performance",
            {"date_start": "2020-01-01", "date_end": "2020-01-31"},
        )

        self.assertEqual(datos["ventas"], 0.0)
        self.assertEqual(datos["filas_de_venta"], 0)


class ParametrosInvalidosTests(DatosDePruebaMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.user = _staff("alejo")

    def test_una_fecha_mal_escrita_devuelve_un_error_que_el_modelo_puede_corregir(self):
        datos = run_tool(self.user, "get_sales", {"date_start": "julio", "date_end": HOY.isoformat()})

        self.assertIn("AAAA-MM-DD", datos["error"])

    def test_un_rango_gigante_se_rechaza_en_vez_de_barrer_la_tabla(self):
        datos = run_tool(self.user, "get_sales", {"date_start": "2010-01-01", "date_end": "2026-12-31"})

        self.assertIn("no puede pasar", datos["error"])

    def test_las_fechas_al_reves_se_ordenan_solas(self):
        datos = run_tool(
            self.user, "get_sales",
            {"date_start": HOY.isoformat(), "date_end": (HOY - timedelta(days=5)).isoformat()},
        )

        self.assertNotIn("error", datos)
        self.assertIn("2026-07-10 a 2026-07-15", datos["periodo"])

    def test_un_group_by_inventado_se_rechaza(self):
        datos = run_tool(
            self.user, "get_sales",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "group_by": "planeta"},
        )

        self.assertIn("group_by debe ser", datos["error"])

    def test_una_consulta_que_no_existe_no_tumba_nada(self):
        datos = run_tool(self.user, "borrar_todo", {})

        self.assertIn("No existe la consulta", datos["error"])

    def test_un_parametro_de_mas_no_tumba_la_consulta(self):
        # El modelo a veces manda campos que no pedimos.
        datos = run_tool(
            self.user, "get_performance",
            {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "inventado": "si"},
        )

        self.assertNotIn("error", datos)


class RegistroDeHerramientasTests(TestCase):
    def test_cada_especificacion_apunta_a_una_funcion_que_existe(self):
        declaradas = {spec["function"]["name"] for spec in TOOL_SPECS}

        self.assertEqual(declaradas, set(TOOLS))

    def test_ninguna_herramienta_escribe(self):
        # Si alguna consulta gana un create/update/delete, esta prueba debe fallar:
        # la Etapa E es de solo lectura y la escritura llega con su propio permiso.
        import inspect

        import reports.ai.tools as modulo

        codigo = inspect.getsource(modulo)
        for prohibido in (".create(", ".update(", ".delete(", ".save(", "update_or_create"):
            self.assertNotIn(prohibido, codigo, f"tools.py no deberia contener {prohibido}")


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class BucleDeHerramientasTests(DatosDePruebaMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.user = _staff("alejo")
        self.client.force_login(self.user)

    def _enviar(self, texto="Cuanto vendimos?"):
        return self.client.post(
            reverse("reports:ai_chat"),
            data=json.dumps({"message": texto}),
            content_type="application/json",
        )

    def _respuestas(self, *secuencia):
        base = {"content": "", "tool_calls": [], "model": "deepseek-chat",
                "prompt_tokens": 100, "completion_tokens": 20, "finish_reason": "stop"}
        return [{**base, **paso} for paso in secuencia]

    @patch("reports.ai.views.deepseek_client")
    def test_una_consulta_se_ejecuta_y_su_resultado_vuelve_al_modelo(self, cliente_falso):
        cliente_falso.return_value.chat.side_effect = self._respuestas(
            {"tool_calls": [{
                "id": "c1",
                "function": {"name": "get_performance", "arguments": json.dumps(
                    {"date_start": HOY.isoformat(), "date_end": HOY.isoformat(), "business_unit": "Uva"}
                )},
            }]},
            {"content": "Uva vendio 10.000.000 COP con un ROAS de 5."},
        )

        respuesta = self._enviar()

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("10.000.000", respuesta.json()["reply"]["content"])
        segunda_llamada = cliente_falso.return_value.chat.call_args_list[1][0][0]
        mensajes_de_herramienta = [m for m in segunda_llamada if m["role"] == "tool"]
        self.assertEqual(len(mensajes_de_herramienta), 1)
        self.assertIn("10.000.000 COP", mensajes_de_herramienta[0]["content"])

    @patch("reports.ai.views.deepseek_client")
    def test_las_herramientas_usadas_quedan_guardadas_en_el_mensaje(self, cliente_falso):
        cliente_falso.return_value.chat.side_effect = self._respuestas(
            {"tool_calls": [{
                "id": "c1",
                "function": {"name": "list_dimensions", "arguments": "{}"},
            }]},
            {"content": "Listo."},
        )

        respuesta = self._enviar()

        from reports.models import AiMessage

        mensaje = AiMessage.objects.get(pk=respuesta.json()["reply"]["id"])
        self.assertEqual([h["name"] for h in mensaje.tools_used], ["list_dimensions"])

    @patch("reports.ai.views.deepseek_client")
    def test_los_tokens_de_todas_las_vueltas_se_suman(self, cliente_falso):
        cliente_falso.return_value.chat.side_effect = self._respuestas(
            {"tool_calls": [{"id": "c1", "function": {"name": "list_dimensions", "arguments": "{}"}}]},
            {"content": "Listo."},
        )

        respuesta = self._enviar()

        from reports.models import AiMessage

        mensaje = AiMessage.objects.get(pk=respuesta.json()["reply"]["id"])
        # Dos vueltas de 100 + 20: cobrar solo la ultima subestimaria el gasto del dia.
        self.assertEqual(mensaje.prompt_tokens, 200)
        self.assertEqual(mensaje.completion_tokens, 40)

    @patch("reports.ai.views.deepseek_client")
    def test_un_modelo_que_no_para_de_consultar_se_corta(self, cliente_falso):
        insistente = {"content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "list_dimensions", "arguments": "{}"}}
        ], "model": "deepseek-chat", "prompt_tokens": 10, "completion_tokens": 5, "finish_reason": "tool_calls"}
        cliente_falso.return_value.chat.side_effect = [insistente] * 4 + self._respuestas(
            {"content": "No pude verificar todo."}
        )

        respuesta = self._enviar()

        self.assertEqual(respuesta.status_code, 200)
        # 4 vueltas con herramientas + 1 cierre sin herramientas.
        self.assertEqual(cliente_falso.return_value.chat.call_count, 5)
        self.assertNotIn("tools", cliente_falso.return_value.chat.call_args_list[-1][1])

    @patch("reports.ai.views.deepseek_client")
    def test_argumentos_ilegibles_no_tumban_la_respuesta(self, cliente_falso):
        cliente_falso.return_value.chat.side_effect = self._respuestas(
            {"tool_calls": [{"id": "c1", "function": {"name": "get_sales", "arguments": "{roto"}}]},
            {"content": "Necesito el periodo."},
        )

        respuesta = self._enviar()

        self.assertEqual(respuesta.status_code, 200)
