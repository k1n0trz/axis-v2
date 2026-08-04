"""Registrar un dato hablando, sin archivo."""
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from reports.ai.data_entry import EntryError, MissingData, apply_entry, describe_entry_types, plan_entry
from reports.ai.permissions import WRITE_GROUP
from reports.models import (
    AdPlatform,
    AiConfigChange,
    BusinessUnit,
    Channel,
    Country,
    DailyAdSpend,
    DailyChannelSale,
    IntegrationRun,
    UserProfile,
)

RESPUESTA_FALSA = {
    "content": "Listo.", "tool_calls": [], "model": "deepseek-chat",
    "prompt_tokens": 40, "completion_tokens": 10, "finish_reason": "stop",
}

PERMISOS = ("change_dailyadspend", "change_dailychannelsale")


def _staff(username="karen", con_llave=True, permisos=PERMISOS):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    if con_llave:
        grupo, _ = Group.objects.get_or_create(name=WRITE_GROUP)
        usuario.groups.add(grupo)
    for codename in permisos:
        usuario.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=usuario.pk)


class CatalogosMixin:
    def crear(self):
        self.bali, _ = BusinessUnit.objects.get_or_create(name="Bali", defaults={"slug": "bali"})
        self.marketplace, _ = BusinessUnit.objects.get_or_create(
            name="Marketplace", defaults={"slug": "marketplace"}
        )
        self.co, _ = Country.objects.get_or_create(name="Colombia", defaults={"code": "CO"})
        self.meta, _ = AdPlatform.objects.get_or_create(name="Meta Ads", defaults={"slug": "meta-ads"})
        self.whatsapp, _ = Channel.objects.get_or_create(
            name="WhatsApp Bali", defaults={"slug": "bali-whatsapp"}
        )
        self.ayer = timezone.localdate() - timedelta(days=1)


class ValidarDatoTests(CatalogosMixin, TestCase):
    def setUp(self):
        self.crear()
        self.user = _staff("estefy")
        self.user.profile.business_units.set([self.bali])

    def test_registra_gasto_con_todo_completo(self):
        plan = plan_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320.000",
        )

        self.assertEqual(plan["despues"], "320000")
        self.assertEqual(plan["fecha"], self.ayer.isoformat())
        self.assertEqual(plan["antes"], "sin dato")

    def test_ayer_y_hoy_se_entienden_pero_una_fecha_rara_se_pregunta(self):
        with self.assertRaises(MissingData) as contexto:
            plan_entry(
                self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
                plataforma="Meta Ads", fecha="la semana pasada", monto="100",
            )

        self.assertIn("Preguntale el dia exacto", str(contexto.exception))

    def test_sin_pais_se_pregunta_en_vez_de_suponer(self):
        # Un dato en el pais equivocado no se nota hasta el cierre de mes.
        with self.assertRaises(MissingData) as contexto:
            plan_entry(
                self.user, "gasto_publicitario", marca="Bali",
                plataforma="Meta Ads", fecha="ayer", monto="100000",
            )

        self.assertIn("Falta el pais", str(contexto.exception))

    def test_sin_plataforma_se_pregunta(self):
        with self.assertRaises(MissingData):
            plan_entry(
                self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
                fecha="ayer", monto="100000",
            )

    def test_una_fecha_futura_se_rechaza(self):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()

        with self.assertRaises(EntryError) as contexto:
            plan_entry(
                self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
                plataforma="Meta Ads", fecha=manana, monto="100000",
            )

        self.assertIn("futuro", str(contexto.exception))

    def test_no_puede_registrar_datos_de_una_marca_que_no_ve(self):
        with self.assertRaises(EntryError) as contexto:
            plan_entry(
                self.user, "gasto_publicitario", marca="Marketplace", pais="Colombia",
                plataforma="Meta Ads", fecha="ayer", monto="100000",
            )

        self.assertIn("no esta entre las marcas que ves", str(contexto.exception))

    def test_el_plan_muestra_el_valor_anterior(self):
        # Pisar 400.000 con 320.000 sin que nadie lo vea seria peor que duplicar.
        DailyAdSpend.objects.create(
            business_unit=self.bali, country=self.co, ad_platform=self.meta,
            spend_date=self.ayer, spend_amount=Decimal("400000"),
        )

        plan = plan_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertEqual(plan["antes"], "400000.00")
        self.assertIn("lo reemplaza", plan["aviso"])

    def test_el_monto_con_puntos_de_miles_se_lee_bien(self):
        plan = plan_entry(
            self.user, "ventas_de_canal", marca="Bali", pais="Colombia",
            canal="WhatsApp Bali", fecha="ayer", monto="1.250.000",
        )

        self.assertEqual(plan["despues"], "1250000")

    def test_el_plan_no_escribe_nada(self):
        plan_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertFalse(DailyAdSpend.objects.exists())

    def test_el_inventario_dice_que_puede_actualizar_esta_persona(self):
        datos = describe_entry_types(self.user)

        self.assertEqual(datos["marcas_que_puede_actualizar"], ["Bali"])
        self.assertTrue(all(t["puede"] for t in datos["tipos"]))


class RegistrarDatoTests(CatalogosMixin, TestCase):
    def setUp(self):
        self.crear()
        self.user = _staff("estefy")
        self.user.profile.business_units.set([self.bali])

    def test_registrar_gasto_crea_la_fila(self):
        apply_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        fila = DailyAdSpend.objects.get()
        self.assertEqual(fila.spend_amount, Decimal("320000"))
        self.assertEqual(fila.source_type, DailyAdSpend.SourceType.MANUAL)
        self.assertIn("estefy", fila.source_file)

    def test_registrar_ventas_guarda_pedidos_y_unidades(self):
        apply_entry(
            self.user, "ventas_de_canal", marca="Bali", pais="Colombia",
            canal="WhatsApp Bali", fecha="ayer", monto="1250000", pedidos="8", unidades="15",
        )

        fila = DailyChannelSale.objects.get()
        self.assertEqual(fila.order_count, 8)
        self.assertEqual(fila.units, 15)

    def test_registrar_dos_veces_corrige_y_no_duplica(self):
        apply_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )
        apply_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="410000",
        )

        self.assertEqual(DailyAdSpend.objects.count(), 1)
        self.assertEqual(DailyAdSpend.objects.get().spend_amount, Decimal("410000"))

    def test_queda_en_las_dos_bitacoras(self):
        apply_entry(
            self.user, "gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertTrue(IntegrationRun.objects.filter(source="IA dato manual").exists())
        fila = AiConfigChange.objects.get()
        self.assertEqual(fila.new_value, "320000")
        self.assertEqual(fila.user, self.user)

    def test_sin_el_permiso_no_registra(self):
        sin_permiso = _staff("otra", permisos=())
        sin_permiso.profile.business_units.set([self.bali])

        with self.assertRaises(EntryError) as contexto:
            apply_entry(
                sin_permiso, "gasto_publicitario", marca="Bali", pais="Colombia",
                plataforma="Meta Ads", fecha="ayer", monto="320000",
            )

        self.assertIn("Te falta el permiso", str(contexto.exception))
        self.assertFalse(DailyAdSpend.objects.exists())


@override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
class EndpointYBotonTests(CatalogosMixin, TestCase):
    def setUp(self):
        self.crear()
        self.user = _staff("estefy")
        self.user.profile.business_units.set([self.bali])
        self.client.force_login(self.user)

    def _registrar(self, **cuerpo):
        return self.client.post(
            reverse("reports:ai_data_entry_apply"),
            data=json.dumps(cuerpo),
            content_type="application/json",
        )

    def test_con_confirmacion_registra(self):
        respuesta = self._registrar(
            confirm=True, kind="gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(DailyAdSpend.objects.exists())

    def test_sin_confirmacion_no_registra(self):
        respuesta = self._registrar(
            kind="gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(DailyAdSpend.objects.exists())

    def test_sin_la_llave_del_grupo_no_registra(self):
        self.client.force_login(_staff("ajena", con_llave=False))

        respuesta = self._registrar(
            confirm=True, kind="gasto_publicitario", marca="Bali", pais="Colombia",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(DailyAdSpend.objects.exists())

    def test_un_dato_validado_ofrece_boton(self):
        respuestas = [
            {**RESPUESTA_FALSA, "tool_calls": [{
                "id": "c1",
                "function": {"name": "preview_data_entry", "arguments": json.dumps({
                    "kind": "gasto_publicitario", "marca": "Bali", "pais": "Colombia",
                    "plataforma": "Meta Ads", "fecha": "ayer", "monto": "320000",
                })},
            }]},
            {**RESPUESTA_FALSA, "content": "Confirma para registrarlo."},
        ]
        with patch("reports.ai.views.deepseek_client") as cliente:
            cliente.return_value.chat.side_effect = respuestas
            respuesta = self.client.post(
                reverse("reports:ai_chat"),
                data=json.dumps({"message": "Ayer el gasto de Meta en Bali fue 320.000"}),
                content_type="application/json",
            )

        self.assertEqual(respuesta.json()["pending_entry"]["monto"], "320000")
        self.assertFalse(DailyAdSpend.objects.exists())

    def test_un_dato_incompleto_no_ofrece_boton(self):
        # Falta el pais: el modelo tiene que preguntarlo, no ofrecer un boton.
        respuestas = [
            {**RESPUESTA_FALSA, "tool_calls": [{
                "id": "c1",
                "function": {"name": "preview_data_entry", "arguments": json.dumps({
                    "kind": "gasto_publicitario", "marca": "Bali",
                    "plataforma": "Meta Ads", "fecha": "ayer", "monto": "320000",
                })},
            }]},
            {**RESPUESTA_FALSA, "content": "De que pais?"},
        ]
        with patch("reports.ai.views.deepseek_client") as cliente:
            cliente.return_value.chat.side_effect = respuestas
            respuesta = self.client.post(
                reverse("reports:ai_chat"),
                data=json.dumps({"message": "Ayer el gasto de Meta en Bali fue 320.000"}),
                content_type="application/json",
            )

        self.assertIsNone(respuesta.json()["pending_entry"])
