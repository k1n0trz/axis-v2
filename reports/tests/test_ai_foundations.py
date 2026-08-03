"""Cimientos de la IA interna: proveedor, techo de gasto y conversaciones.

El techo de gasto entra desde el primer commit y no despues. Un widget de chat en
todas las paginas puede convertirse en muchas llamadas sin que nadie lo note, y el
costo no avisa hasta que llega la factura.
"""
from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from reports.ai.budget import BudgetExceeded, check_budget, cost_for, usage_today
from reports.ai.providers import AiProviderError, OpenAICompatibleClient, deepseek_client
from reports.models import AiConversation, AiMessage


class RespuestaFalsa:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        return self._payload


RESPUESTA_OK = {
    "model": "deepseek-chat",
    "choices": [{"message": {"content": "Uva vendio 12 millones en julio."}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1200, "completion_tokens": 80},
}


@override_settings(DEEPSEEK_API_KEY="sk-prueba", AI_MAX_RETRIES=2)
class ProveedorTests(TestCase):
    def test_una_respuesta_normal_trae_texto_y_tokens(self):
        with patch.object(OpenAICompatibleClient, "chat", wraps=None):
            pass  # se prueba el cliente real abajo
        cliente = deepseek_client()
        with patch.object(cliente.session, "post", return_value=RespuestaFalsa(payload=RESPUESTA_OK)):
            salida = cliente.chat([{"role": "user", "content": "hola"}])

        self.assertIn("12 millones", salida["content"])
        self.assertEqual(salida["prompt_tokens"], 1200)
        self.assertEqual(salida["completion_tokens"], 80)

    def test_reintenta_un_500_y_termina_bien(self):
        cliente = deepseek_client()
        respuestas = [RespuestaFalsa(status_code=503), RespuestaFalsa(payload=RESPUESTA_OK)]
        with patch.object(cliente.session, "post", side_effect=respuestas) as post:
            salida = cliente.chat([{"role": "user", "content": "hola"}])

        self.assertEqual(post.call_count, 2)
        self.assertIn("12 millones", salida["content"])

    def test_un_401_no_se_reintenta(self):
        # No va a mejorar solo: dejar al usuario esperando tres veces no ayuda.
        cliente = deepseek_client()
        with patch.object(cliente.session, "post", return_value=RespuestaFalsa(status_code=401, text="bad key")) as post:
            with self.assertRaises(AiProviderError):
                cliente.chat([{"role": "user", "content": "hola"}])

        self.assertEqual(post.call_count, 1)

    def test_si_la_red_falla_siempre_lo_dice_claro(self):
        cliente = deepseek_client()
        with patch.object(cliente.session, "post", side_effect=requests.ConnectionError("sin red")):
            with self.assertRaises(AiProviderError) as ctx:
                cliente.chat([{"role": "user", "content": "hola"}])

        self.assertIn("no respondio", str(ctx.exception))

    @override_settings(DEEPSEEK_API_KEY="")
    def test_sin_clave_no_intenta_llamar(self):
        cliente = deepseek_client()
        self.assertFalse(cliente.is_configured)
        with self.assertRaises(AiProviderError):
            cliente.chat([{"role": "user", "content": "hola"}])


class TechoDeGastoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alejo", password="secreto", is_staff=True)
        self.conversacion = AiConversation.objects.create(user=self.user, title="prueba")

    def _mensaje(self, prompt, completion):
        AiMessage.objects.create(
            conversation=self.conversacion,
            role=AiMessage.Role.ASSISTANT,
            content="x",
            prompt_tokens=prompt,
            completion_tokens=completion,
            cost_usd=cost_for(prompt, completion),
        )

    def test_el_costo_sale_de_los_precios_configurados(self):
        with self.settings(AI_INPUT_COST_PER_MTOK="1.00", AI_OUTPUT_COST_PER_MTOK="2.00"):
            self.assertEqual(cost_for(1_000_000, 0), Decimal("1.000000"))
            self.assertEqual(cost_for(0, 500_000), Decimal("1.000000"))

    def test_suma_lo_gastado_hoy_por_ese_usuario(self):
        self._mensaje(1000, 100)
        self._mensaje(2000, 200)

        gastado = usage_today(self.user)

        self.assertEqual(gastado["tokens"], 3300)
        self.assertGreater(gastado["cost_usd"], Decimal("0"))

    def test_no_mezcla_el_gasto_de_otro_usuario(self):
        otro = User.objects.create_user(username="valentina", password="secreto")
        AiMessage.objects.create(
            conversation=AiConversation.objects.create(user=otro),
            role=AiMessage.Role.ASSISTANT, prompt_tokens=99999, completion_tokens=0,
        )
        self._mensaje(1000, 0)

        self.assertEqual(usage_today(self.user)["tokens"], 1000)

    @override_settings(AI_DAILY_TOKEN_BUDGET=2000, AI_DAILY_COST_LIMIT_USD="999")
    def test_corta_por_tokens(self):
        self._mensaje(1900, 200)

        with self.assertRaises(BudgetExceeded) as ctx:
            check_budget(self.user)
        self.assertIn("2,000 tokens", str(ctx.exception))

    @override_settings(AI_DAILY_TOKEN_BUDGET=0, AI_DAILY_COST_LIMIT_USD="0.001")
    def test_corta_por_costo(self):
        self._mensaje(100000, 10000)

        with self.assertRaises(BudgetExceeded):
            check_budget(self.user)

    @override_settings(AI_DAILY_TOKEN_BUDGET=400000, AI_DAILY_COST_LIMIT_USD="2.00")
    def test_con_cupo_disponible_deja_pasar(self):
        self._mensaje(1000, 100)

        gastado = check_budget(self.user)

        self.assertEqual(gastado["tokens"], 1100)


class ConversacionTests(TestCase):
    def test_el_costo_queda_congelado_en_el_mensaje(self):
        # Si se recalculara con el precio de hoy, el historico no serviria para auditar.
        user = User.objects.create_user(username="alejo", password="x")
        conversacion = AiConversation.objects.create(user=user)
        with self.settings(AI_INPUT_COST_PER_MTOK="10.00", AI_OUTPUT_COST_PER_MTOK="10.00"):
            mensaje = AiMessage.objects.create(
                conversation=conversacion, role=AiMessage.Role.ASSISTANT,
                prompt_tokens=1_000_000, completion_tokens=0, cost_usd=cost_for(1_000_000, 0),
            )
        with self.settings(AI_INPUT_COST_PER_MTOK="0.01"):
            mensaje.refresh_from_db()
            self.assertEqual(mensaje.cost_usd, Decimal("10.000000"))

    def test_los_mensajes_quedan_en_orden(self):
        user = User.objects.create_user(username="alejo", password="x")
        conversacion = AiConversation.objects.create(user=user)
        for rol in (AiMessage.Role.USER, AiMessage.Role.ASSISTANT, AiMessage.Role.USER):
            AiMessage.objects.create(conversation=conversacion, role=rol, content=rol)

        roles = list(conversacion.messages.values_list("role", flat=True))

        self.assertEqual(roles, ["user", "assistant", "user"])
        self.assertEqual(conversacion.messages.first().total_tokens, 0)
