"""Memoria de la IA: guardar, recuperar, olvidar y destilar."""
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.ai.distill import distill_conversation, summarize_conversation
from reports.ai.memory import (
    MAX_ACTIVE_PER_USER,
    forget,
    mark_used,
    memory_blocks,
    relevant_memories,
    remember,
)
from reports.models import AiConversation, AiMemory, AiMessage, UserProfile

RESPUESTA_FALSA = {
    "content": "Con gusto.",
    "tool_calls": [],
    "model": "deepseek-chat",
    "prompt_tokens": 100,
    "completion_tokens": 20,
    "finish_reason": "stop",
}


def _staff(username):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    return usuario


class GuardarMemoriasTests(TestCase):
    def setUp(self):
        self.user = _staff("alejo")

    def test_una_nota_muy_corta_no_se_guarda(self):
        self.assertIsNone(remember(self.user, "ok"))
        self.assertFalse(AiMemory.objects.exists())

    def test_la_misma_nota_no_se_guarda_dos_veces(self):
        remember(self.user, "Prefiere respuestas cortas y sin rodeos")
        remember(self.user, "Prefiere respuestas cortas y sin rodeos")

        self.assertEqual(AiMemory.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_una_nota_contenida_en_otra_no_duplica_y_conserva_el_detalle(self):
        remember(self.user, "Prefiere respuestas cortas")
        remember(self.user, "Prefiere respuestas cortas y sin rodeos, en español")

        activas = AiMemory.objects.filter(user=self.user, is_active=True)
        self.assertEqual(activas.count(), 1)
        self.assertIn("sin rodeos", activas.first().content)

    def test_pasar_del_techo_retira_las_menos_usadas(self):
        for indice in range(MAX_ACTIVE_PER_USER + 3):
            remember(self.user, f"Nota numero {indice} sobre la operacion diaria")

        self.assertEqual(
            AiMemory.objects.filter(user=self.user, is_active=True).count(), MAX_ACTIVE_PER_USER
        )
        # Nada se borra de verdad: quedan inactivas.
        self.assertEqual(AiMemory.objects.filter(user=self.user).count(), MAX_ACTIVE_PER_USER + 3)

    def test_olvidar_es_soft_delete(self):
        memoria = remember(self.user, "Trabaja los reportes los lunes temprano")

        forget(self.user, memoria.pk)

        memoria.refresh_from_db()
        self.assertFalse(memoria.is_active)

    def test_nadie_puede_olvidar_las_notas_de_otro(self):
        memoria = remember(self.user, "Trabaja los reportes los lunes temprano")
        otro = _staff("otra-persona")

        self.assertEqual(forget(otro, memoria.pk), 0)
        memoria.refresh_from_db()
        self.assertTrue(memoria.is_active)


class RecuperarMemoriasTests(TestCase):
    def setUp(self):
        self.user = _staff("alejo")

    def test_recupera_la_nota_que_comparte_palabras_con_la_pregunta(self):
        remember(self.user, "Trabaja principalmente con la marca DistriSex mayorista")
        remember(self.user, "Revisa las webs los viernes")

        encontradas = relevant_memories(self.user, "Como voy con DistriSex?")

        self.assertTrue(encontradas)
        self.assertIn("DistriSex", encontradas[0].content)

    def test_sin_coincidencia_devuelve_las_mas_usadas(self):
        # Una preferencia de estilo aplica siempre, aunque no comparta palabras.
        memoria = remember(self.user, "Prefiere respuestas cortas y sin rodeos")
        mark_used([memoria])

        encontradas = relevant_memories(self.user, "xyzabc qwerty")

        self.assertEqual([m.pk for m in encontradas], [memoria.pk])

    def test_no_recupera_notas_de_otro_usuario(self):
        otro = _staff("otra-persona")
        remember(otro, "Trabaja principalmente con la marca DistriSex mayorista")

        self.assertEqual(relevant_memories(self.user, "DistriSex"), [])

    def test_no_recupera_notas_retiradas(self):
        memoria = remember(self.user, "Trabaja principalmente con DistriSex mayorista")
        forget(self.user, memoria.pk)

        self.assertEqual(relevant_memories(self.user, "DistriSex"), [])

    def test_usar_una_nota_queda_registrado(self):
        memoria = remember(self.user, "Revisa las webs los viernes por la tarde")

        mark_used([memoria])

        memoria.refresh_from_db()
        self.assertEqual(memoria.times_used, 1)
        self.assertIsNotNone(memoria.last_used_at)

    def test_el_contexto_deducido_va_marcado_como_referencia(self):
        memoria = remember(
            self.user, "Revisa las webs los viernes por la tarde", kind=AiMemory.Kind.CONTEXT
        )

        contexto, reglas = memory_blocks([memoria])

        self.assertIn("no instrucciones", contexto)
        self.assertIn("Revisa las webs", contexto)
        self.assertEqual(reglas, [])

    def test_una_preferencia_del_usuario_si_va_como_orden(self):
        # En una prueba real el modelo se salto "maximo dos frases" porque el bloque
        # decia que las notas no eran instrucciones. Lo que la persona pidio, si lo es.
        memoria = remember(
            self.user, "Prefiere respuestas de maximo dos frases", kind=AiMemory.Kind.PREFERENCE
        )

        contexto, reglas = memory_blocks([memoria])

        self.assertEqual(reglas, ["Prefiere respuestas de maximo dos frases"])
        self.assertEqual(contexto, "")

    def test_ordenes_y_contexto_van_en_bloques_distintos(self):
        estilo = remember(
            self.user, "Prefiere respuestas de maximo dos frases", kind=AiMemory.Kind.STYLE
        )
        dato = remember(
            self.user, "En DistriSex el ROAS no es medible por la poca pauta",
            kind=AiMemory.Kind.CONTEXT,
        )

        contexto, reglas = memory_blocks([estilo, dato])

        self.assertEqual(reglas, ["Prefiere respuestas de maximo dos frases"])
        self.assertIn("ROAS no es medible", contexto)


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class MemoriaEnElChatTests(TestCase):
    def setUp(self):
        self.user = _staff("alejo")
        self.client.force_login(self.user)
        self.chat_url = reverse("reports:ai_chat")

    def _enviar(self, texto):
        return self.client.post(
            self.chat_url, data=json.dumps({"message": texto}), content_type="application/json"
        )

    @patch("reports.ai.views.deepseek_client")
    def test_recuerda_que_guarda_la_nota_sin_llamar_de_mas(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA

        respuesta = self._enviar("Recuerda que en DistriSex el ROAS no es medible")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("DistriSex", respuesta.json()["remembered"])
        self.assertEqual(AiMemory.objects.filter(user=self.user).count(), 1)
        # Una sola llamada: la nota venia dicha, no hay que deducirla.
        self.assertEqual(cliente_falso.return_value.chat.call_count, 1)

    @patch("reports.ai.views.deepseek_client")
    def test_las_notas_viajan_en_el_prompt_como_bloque_aparte(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        remember(self.user, "Trabaja principalmente con la marca DistriSex mayorista")

        self._enviar("Que tal va DistriSex?")

        enviados = cliente_falso.return_value.chat.call_args[0][0]
        bloques = [m["content"] for m in enviados if m["role"] == "system"]
        self.assertTrue(any("DistriSex mayorista" in b for b in bloques))

    @patch("reports.ai.views.deepseek_client")
    def test_el_resumen_reemplaza_los_turnos_ya_comprimidos(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Primera pregunta")
        conversacion = AiConversation.objects.get(user=self.user)
        conversacion.summary = "Hablaron de la pauta de Uva Colombia."
        conversacion.summarized_until = conversacion.messages.last().pk
        conversacion.save()

        self._enviar("Segunda pregunta")

        enviados = cliente_falso.return_value.chat.call_args[0][0]
        contenidos = [m["content"] for m in enviados]
        self.assertTrue(any("pauta de Uva Colombia" in c for c in contenidos))
        self.assertNotIn("Primera pregunta", contenidos)

    @patch("reports.ai.views.deepseek_client")
    def test_el_usuario_ve_y_puede_borrar_lo_que_la_ia_recuerda(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Recuerda que los reportes se revisan los lunes")
        memoria = AiMemory.objects.get(user=self.user)

        listado = self.client.get(reverse("reports:ai_memories")).json()
        self.assertEqual(len(listado["memories"]), 1)

        borrado = self.client.post(reverse("reports:ai_memory_forget", args=[memoria.pk]))
        self.assertEqual(borrado.status_code, 200)
        self.assertEqual(self.client.get(reverse("reports:ai_memories")).json()["memories"], [])

    @patch("reports.ai.views.deepseek_client")
    def test_el_pulgar_queda_guardado_en_el_mensaje(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        respuesta = self._enviar("Una pregunta cualquiera")
        mensaje_id = respuesta.json()["reply"]["id"]

        self.client.post(
            reverse("reports:ai_feedback"),
            data=json.dumps({"message_id": mensaje_id, "feedback": "down"}),
            content_type="application/json",
        )

        self.assertEqual(AiMessage.objects.get(pk=mensaje_id).feedback, "down")

    @patch("reports.ai.views.deepseek_client")
    def test_no_se_puede_calificar_el_mensaje_de_otro(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        respuesta = self._enviar("Una pregunta cualquiera")
        mensaje_id = respuesta.json()["reply"]["id"]

        otro = _staff("otra-persona")
        self.client.force_login(otro)
        calificacion = self.client.post(
            reverse("reports:ai_feedback"),
            data=json.dumps({"message_id": mensaje_id, "feedback": "up"}),
            content_type="application/json",
        )

        self.assertEqual(calificacion.status_code, 404)
        self.assertEqual(AiMessage.objects.get(pk=mensaje_id).feedback, "")


class DistilacionTests(TestCase):
    def setUp(self):
        self.user = _staff("alejo")
        self.conversacion = AiConversation.objects.create(user=self.user, session_key="s1")
        AiMessage.objects.create(
            conversation=self.conversacion, role="user", content="Prefiero que me respondas corto."
        )
        self.respuesta = AiMessage.objects.create(
            conversation=self.conversacion, role="assistant", content="Entendido."
        )

    def _cliente(self, contenido):
        class ClienteFalso:
            def __init__(self):
                self.recibido = []

            def chat(self, messages, **kwargs):
                self.recibido.append(messages)
                return {**RESPUESTA_FALSA, "content": contenido}

        return ClienteFalso()

    def test_las_notas_extraidas_se_guardan(self):
        cliente = self._cliente(
            '{"memories": [{"kind": "style", "content": "Prefiere respuestas cortas y directas"}]}'
        )

        creadas = distill_conversation(self.conversacion, client=cliente)

        self.assertEqual(len(creadas), 1)
        self.assertEqual(creadas[0].kind, "style")
        self.assertEqual(creadas[0].origin, AiMemory.Origin.DISTILLED)

    def test_un_json_envuelto_en_bloque_de_codigo_igual_se_lee(self):
        cliente = self._cliente(
            '```json\n{"memories": [{"kind": "style", "content": "Prefiere respuestas cortas"}]}\n```'
        )

        self.assertEqual(len(distill_conversation(self.conversacion, client=cliente)), 1)

    def test_una_respuesta_ilegible_no_tumba_la_corrida(self):
        cliente = self._cliente("no era JSON")

        self.assertEqual(distill_conversation(self.conversacion, client=cliente), [])
        self.conversacion.refresh_from_db()
        self.assertIsNotNone(self.conversacion.distilled_at)

    def test_no_aprende_de_una_respuesta_con_pulgar_abajo(self):
        self.respuesta.feedback = AiMessage.Feedback.DOWN
        self.respuesta.save(update_fields=["feedback"])
        cliente = self._cliente('{"memories": []}')

        distill_conversation(self.conversacion, client=cliente)

        enviado = cliente.recibido[0][-1]["content"]
        self.assertNotIn("Entendido.", enviado)

    def test_si_el_proveedor_falla_la_conversacion_no_queda_destilada(self):
        from reports.ai.providers import AiProviderError

        class ClienteRoto:
            def chat(self, messages, **kwargs):
                raise AiProviderError("sin respuesta")

        self.assertEqual(distill_conversation(self.conversacion, client=ClienteRoto()), [])
        self.conversacion.refresh_from_db()
        # Se vuelve a intentar mañana.
        self.assertIsNone(self.conversacion.distilled_at)

    def test_una_conversacion_corta_no_se_resume(self):
        cliente = self._cliente("Un resumen.")

        self.assertFalse(summarize_conversation(self.conversacion, client=cliente))

    def test_una_conversacion_larga_se_resume_y_marca_hasta_donde(self):
        for indice in range(16):
            AiMessage.objects.create(
                conversation=self.conversacion,
                role="user" if indice % 2 == 0 else "assistant",
                content=f"Turno numero {indice}",
            )
        cliente = self._cliente("Hablaron de la pauta de Uva.")

        self.assertTrue(summarize_conversation(self.conversacion, client=cliente))

        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.summary, "Hablaron de la pauta de Uva.")
        self.assertGreater(self.conversacion.summarized_until, 0)


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class PosicionDeLosBloquesTests(TestCase):
    """Donde va cada bloque en la lista de mensajes."""

    def setUp(self):
        self.user = _staff("alejo")
        self.client.force_login(self.user)

    @patch("reports.ai.views.deepseek_client")
    def test_el_contexto_se_queda_arriba_con_el_encuadre(self, cliente_falso):
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        remember(self.user, "En DistriSex el ROAS no es medible", kind=AiMemory.Kind.CONTEXT)

        self.client.post(
            reverse("reports:ai_chat"),
            data=json.dumps({"message": "Como va DistriSex?"}),
            content_type="application/json",
        )

        enviados = cliente_falso.return_value.chat.call_args[0][0]
        self.assertIn("ROAS no es medible", enviados[1]["content"])

    @patch("reports.ai.views.deepseek_client")
    def test_la_regla_de_estilo_tambien_entra_en_el_prompt_de_sistema(self, cliente_falso):
        # En un mensaje aparte competia con "Como debes responder" y perdia.
        cliente_falso.return_value.chat.return_value = RESPUESTA_FALSA
        remember(self.user, "Responde en maximo dos frases", kind=AiMemory.Kind.STYLE)

        self.client.post(
            reverse("reports:ai_chat"),
            data=json.dumps({"message": "Que reviso hoy?"}),
            content_type="application/json",
        )

        enviados = cliente_falso.return_value.chat.call_args[0][0]
        self.assertIn("maximo dos frases", enviados[0]["content"])
        self.assertIn("lo pidio esta persona", enviados[0]["content"])
