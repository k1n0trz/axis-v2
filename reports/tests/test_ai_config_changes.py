"""Cambios de configuracion que la IA propone y una persona aplica."""
import json
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from reports.ai.config_changes import ConfigError, apply_change, describe_config, plan_change
from reports.ai.permissions import WRITE_GROUP
from reports.models import (
    AiConfigChange,
    BusinessUnit,
    IntegrationRun,
    RoasTrafficLightSetting,
    UserProfile,
)

RESPUESTA_FALSA = {
    "content": "Listo.",
    "tool_calls": [],
    "model": "deepseek-chat",
    "prompt_tokens": 50,
    "completion_tokens": 10,
    "finish_reason": "stop",
}

PERMISOS_POR_DEFECTO = ("change_businessunit", "change_roastrafficlightsetting")


def _staff(username="alejo", con_llave=True, permisos=PERMISOS_POR_DEFECTO):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    if con_llave:
        grupo, _ = Group.objects.get_or_create(name=WRITE_GROUP)
        usuario.groups.add(grupo)
    for codename in permisos:
        usuario.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=usuario.pk)


class LoQueSePuedeCambiarTests(TestCase):
    def setUp(self):
        self.user = _staff()
        self.marca, _ = BusinessUnit.objects.get_or_create(name="Uva", defaults={"slug": "uva"})

    def test_el_inventario_dice_que_los_colores_no_estan_aca(self):
        # Prometer que se cambian los colores cuando no hay donde guardarlos es peor
        # que decir que no se puede.
        datos = describe_config(self.user)

        self.assertIn("cambio de codigo", datos["nota"])

    def test_un_modelo_que_no_esta_en_la_lista_blanca_se_rechaza(self):
        with self.assertRaises(ConfigError) as contexto:
            plan_change(self.user, "usuarios", "alejo", "nombre", "otro")

        self.assertIn("no se puede cambiar por aqui", str(contexto.exception))

    def test_un_campo_que_no_esta_en_la_lista_blanca_se_rechaza(self):
        # `slug` no se puede tocar: los importadores eligen la marca por slug.
        with self.assertRaises(ConfigError) as contexto:
            plan_change(self.user, "marca", "Uva", "slug", "uva-nueva")

        self.assertIn("solo se puede cambiar", str(contexto.exception))

    def test_un_objeto_que_no_existe_lista_los_que_hay(self):
        with self.assertRaises(ConfigError) as contexto:
            plan_change(self.user, "marca", "Inventada", "nombre", "Otra")

        self.assertIn("Uva", str(contexto.exception))

    def test_un_valor_del_tipo_equivocado_se_rechaza(self):
        with self.assertRaises(ConfigError) as contexto:
            plan_change(self.user, "marca", "Uva", "orden", "primero")

        self.assertIn("no es un numero entero", str(contexto.exception))

    def test_cambiar_algo_a_lo_que_ya_vale_se_avisa(self):
        with self.assertRaises(ConfigError) as contexto:
            plan_change(self.user, "marca", "Uva", "nombre", "Uva")

        self.assertIn("no hay nada que cambiar", str(contexto.exception))

    def test_desactivar_una_marca_avisa_que_no_borra_datos(self):
        plan = plan_change(self.user, "marca", "Uva", "activa", "no")

        self.assertIn("no se borran", plan["aviso"])

    def test_el_plan_no_escribe_nada(self):
        plan_change(self.user, "marca", "Uva", "nombre", "Uva Nueva")

        self.marca.refresh_from_db()
        self.assertEqual(self.marca.name, "Uva")


class AplicarCambiosTests(TestCase):
    def setUp(self):
        self.user = _staff()
        self.marca, _ = BusinessUnit.objects.get_or_create(name="Uva", defaults={"slug": "uva"})
        BusinessUnit.objects.filter(pk=self.marca.pk).update(display_order=0)
        self.marca.refresh_from_db()
        self.semaforo, _ = RoasTrafficLightSetting.objects.get_or_create(name="Semaforo ROAS")

    def test_aplicar_cambia_el_dato_y_deja_bitacora(self):
        resultado = apply_change(self.user, "marca", "Uva", "orden", "7")

        self.marca.refresh_from_db()
        self.assertEqual(self.marca.display_order, 7)
        self.assertTrue(resultado["aplicado"])
        self.assertTrue(AiConfigChange.objects.filter(field="orden").exists())
        self.assertTrue(IntegrationRun.objects.filter(source="IA configuracion").exists())

    def test_la_bitacora_guarda_el_antes_y_el_despues(self):
        apply_change(self.user, "marca", "Uva", "orden", "9")

        fila = AiConfigChange.objects.get(field="orden")
        self.assertEqual(fila.new_value, "9")
        self.assertEqual(fila.user, self.user)

    def test_sin_el_permiso_del_modelo_no_aplica(self):
        sin_permiso = _staff("analista", permisos=())

        with self.assertRaises(ConfigError) as contexto:
            apply_change(sin_permiso, "marca", "Uva", "orden", "3")

        self.assertIn("Te falta el permiso", str(contexto.exception))
        self.marca.refresh_from_db()
        self.assertEqual(self.marca.display_order, 0)

    def test_la_restriccion_del_modelo_se_respeta(self):
        # La base exige amarillo <= verde: sin full_clean esto seria un IntegrityError
        # feo en vez de un mensaje.
        with self.assertRaises(ValidationError):
            apply_change(self.user, "semaforo_roas", "Semaforo ROAS", "amarillo_desde", "99")


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class EndpointDeConfiguracionTests(TestCase):
    def setUp(self):
        self.user = _staff()
        self.client.force_login(self.user)
        self.marca, _ = BusinessUnit.objects.get_or_create(name="Uva", defaults={"slug": "uva"})
        BusinessUnit.objects.filter(pk=self.marca.pk).update(display_order=0)
        self.marca.refresh_from_db()

    def _aplicar(self, **cuerpo):
        return self.client.post(
            reverse("reports:ai_config_apply"),
            data=json.dumps(cuerpo),
            content_type="application/json",
        )

    def test_con_confirmacion_aplica(self):
        respuesta = self._aplicar(confirm=True, target="marca", name="Uva", field="orden", value="4")

        self.assertEqual(respuesta.status_code, 200)
        self.marca.refresh_from_db()
        self.assertEqual(self.marca.display_order, 4)

    def test_sin_confirmacion_no_aplica(self):
        respuesta = self._aplicar(target="marca", name="Uva", field="orden", value="4")

        self.assertEqual(respuesta.status_code, 400)
        self.marca.refresh_from_db()
        self.assertEqual(self.marca.display_order, 0)

    def test_sin_la_llave_del_grupo_responde_403(self):
        self.client.force_login(_staff("karen", con_llave=False))

        respuesta = self._aplicar(confirm=True, target="marca", name="Uva", field="orden", value="4")

        self.assertEqual(respuesta.status_code, 403)
        self.marca.refresh_from_db()
        self.assertEqual(self.marca.display_order, 0)

    def test_un_umbral_invalido_devuelve_mensaje_y_no_500(self):
        RoasTrafficLightSetting.objects.get_or_create(name="Semaforo ROAS")

        respuesta = self._aplicar(
            confirm=True,
            target="semaforo_roas",
            name="Semaforo ROAS",
            field="amarillo_desde",
            value="99",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("detail", respuesta.json())


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class BotonDesdeLaHerramientaTests(TestCase):
    """El boton sale de la herramienta validada, no del texto del modelo."""

    def setUp(self):
        self.user = _staff()
        self.client.force_login(self.user)
        BusinessUnit.objects.get_or_create(name="Uva", defaults={"slug": "uva"})

    def _preguntar(self, tool_calls):
        respuestas = [
            {**RESPUESTA_FALSA, "tool_calls": tool_calls},
            {**RESPUESTA_FALSA, "content": "Listo, confirma."},
        ]
        with patch("reports.ai.views.deepseek_client") as cliente:
            cliente.return_value.chat.side_effect = respuestas
            return self.client.post(
                reverse("reports:ai_chat"),
                data=json.dumps({"message": "Cambia el orden de Uva a 5"}),
                content_type="application/json",
            )

    def test_un_cambio_valido_ofrece_boton(self):
        respuesta = self._preguntar([{
            "id": "c1",
            "function": {
                "name": "preview_config_change",
                "arguments": json.dumps(
                    {"target": "marca", "name": "Uva", "field": "orden", "value": "5"}
                ),
            },
        }])

        pendiente = respuesta.json()["pending_change"]
        self.assertEqual(pendiente["value"], "5")

    def test_un_cambio_invalido_no_ofrece_boton(self):
        # Sin esto se ofreceria aplicar un cambio que la validacion ya rechazo.
        respuesta = self._preguntar([{
            "id": "c1",
            "function": {
                "name": "preview_config_change",
                "arguments": json.dumps(
                    {"target": "marca", "name": "Inventada", "field": "orden", "value": "5"}
                ),
            },
        }])

        self.assertIsNone(respuesta.json()["pending_change"])

    def test_una_pregunta_sin_cambios_no_ofrece_boton(self):
        respuesta = self._preguntar([{
            "id": "c1",
            "function": {"name": "get_config", "arguments": "{}"},
        }])

        self.assertIsNone(respuesta.json()["pending_change"])

    def test_el_inventario_aclara_que_no_crea_ni_borra(self):
        # El modelo dijo en una prueba real que podia "añadir" marcas. No puede.
        datos = describe_config(self.user)

        self.assertIn("crear una marca", datos["nota"])
        self.assertIn("desactivar", datos["nota"])
