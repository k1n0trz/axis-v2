"""Volver a una conversacion anterior.

Las conversaciones se guardaban desde la Etapa C, pero el widget solo cargaba la de la
sesion del navegador actual: al cambiar de sesion quedaban guardadas y sin forma de
verlas, que para quien las escribio es lo mismo que haberlas perdido.
"""
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.models import AiConversation, AiMessage, UserProfile

RESPUESTA_FALSA = {
    "content": "Con gusto.",
    "tool_calls": [],
    "model": "deepseek-chat",
    "prompt_tokens": 40,
    "completion_tokens": 10,
    "finish_reason": "stop",
}


def _staff(username="alejo"):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    return usuario


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class HistorialDeConversacionesTests(TestCase):
    def setUp(self):
        self.user = _staff()
        self.client.force_login(self.user)

    def _enviar(self, texto, conversation_id=None):
        cuerpo = {"message": texto}
        if conversation_id:
            cuerpo["conversation_id"] = conversation_id
        return self.client.post(
            reverse("reports:ai_chat"), data=json.dumps(cuerpo), content_type="application/json"
        )

    @patch("reports.ai.views.deepseek_client")
    def test_el_listado_muestra_las_conversaciones_de_esta_persona(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Primera pregunta de julio")

        datos = self.client.get(reverse("reports:ai_conversations")).json()

        self.assertEqual(len(datos["conversations"]), 1)
        self.assertEqual(datos["conversations"][0]["messages"], 2)
        self.assertIn("Primera pregunta", datos["conversations"][0]["title"])

    @patch("reports.ai.views.deepseek_client")
    def test_el_listado_no_muestra_las_de_otro_usuario(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Mi pregunta")
        self.client.force_login(_staff("karen"))

        datos = self.client.get(reverse("reports:ai_conversations")).json()

        self.assertEqual(datos["conversations"], [])

    @patch("reports.ai.views.deepseek_client")
    def test_una_conversacion_vacia_no_aparece_en_el_listado(self, cliente):
        AiConversation.objects.create(user=self.user, session_key="vieja")

        datos = self.client.get(reverse("reports:ai_conversations")).json()

        self.assertEqual(datos["conversations"], [])

    @patch("reports.ai.views.deepseek_client")
    def test_se_puede_abrir_una_conversacion_por_id(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Pregunta de la sesion vieja")
        vieja = AiConversation.objects.get()
        # Simula otra sesion del navegador: la conversacion ya no es "la actual".
        AiConversation.objects.filter(pk=vieja.pk).update(session_key="otra-sesion")

        datos = self.client.get(
            reverse("reports:ai_history") + f"?conversation={vieja.pk}"
        ).json()

        self.assertEqual(datos["conversation_id"], vieja.pk)
        self.assertIn("sesion vieja", datos["messages"][0]["content"])

    @patch("reports.ai.views.deepseek_client")
    def test_no_se_puede_abrir_la_conversacion_de_otro(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Mi pregunta privada")
        ajena = AiConversation.objects.get()

        self.client.force_login(_staff("karen"))
        datos = self.client.get(
            reverse("reports:ai_history") + f"?conversation={ajena.pk}"
        ).json()

        # Cae a la conversacion propia (ninguna), no a la ajena.
        self.assertNotEqual(datos["conversation_id"], ajena.pk)
        self.assertEqual(datos["messages"], [])

    @patch("reports.ai.views.deepseek_client")
    def test_se_puede_continuar_una_conversacion_vieja(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Primera")
        vieja = AiConversation.objects.get()
        AiConversation.objects.filter(pk=vieja.pk).update(session_key="otra-sesion")

        self._enviar("Segunda", conversation_id=vieja.pk)

        self.assertEqual(AiConversation.objects.count(), 1)
        self.assertEqual(vieja.messages.count(), 4)

    @patch("reports.ai.views.deepseek_client")
    def test_no_se_puede_escribir_en_la_conversacion_de_otro(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Mi pregunta")
        ajena = AiConversation.objects.get()

        self.client.force_login(_staff("karen"))
        self._enviar("Me cuelo", conversation_id=ajena.pk)

        # El mensaje de Karen abrio su propia conversacion, no toco la ajena.
        self.assertEqual(ajena.messages.count(), 2)
        self.assertEqual(AiConversation.objects.count(), 2)

    @patch("reports.ai.views.deepseek_client")
    def test_una_conversacion_nueva_no_borra_la_anterior(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Primera")

        respuesta = self.client.post(reverse("reports:ai_conversation_new"))

        nueva_id = respuesta.json()["conversation_id"]
        self.assertEqual(AiConversation.objects.count(), 2)
        self.assertEqual(AiMessage.objects.filter(conversation_id=nueva_id).count(), 0)
        self.assertEqual(AiMessage.objects.count(), 2)

    @patch("reports.ai.views.deepseek_client")
    def test_tras_abrir_una_nueva_los_mensajes_van_ahi(self, cliente):
        cliente.return_value.chat.return_value = RESPUESTA_FALSA
        self._enviar("Primera")
        nueva_id = self.client.post(reverse("reports:ai_conversation_new")).json()["conversation_id"]

        self._enviar("En la nueva", conversation_id=nueva_id)

        self.assertEqual(AiMessage.objects.filter(conversation_id=nueva_id).count(), 2)
