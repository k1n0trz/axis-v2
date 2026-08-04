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
        # Dos paises a proposito: con uno solo el pais se infiere y no habria nada que
        # preguntar, que es justo lo que prueba `PaisInferidoTests`.
        self.ec, _ = Country.objects.get_or_create(name="Ecuador", defaults={"code": "EC"})
        self.bali.countries.set([self.co, self.ec])
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

        self.assertIn("Preguntale de cual es", str(contexto.exception))

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

    def test_sin_permiso_de_django_no_registra(self):
        # La llave del grupo ya no hace falta para los datos propios: lo que manda es el
        # permiso de Django, que es lo que esta persona ya usa en el admin.
        ajena = _staff("ajena", con_llave=False, permisos=())
        ajena.profile.business_units.set([self.bali])
        self.client.force_login(ajena)

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
        # Sin plataforma no se puede inferir nada: el modelo tiene que preguntarla.
        respuestas = [
            {**RESPUESTA_FALSA, "tool_calls": [{
                "id": "c1",
                "function": {"name": "preview_data_entry", "arguments": json.dumps({
                    "kind": "gasto_publicitario", "marca": "Bali",
                    "fecha": "ayer", "monto": "320000",
                })},
            }]},
            {**RESPUESTA_FALSA, "content": "De que plataforma?"},
        ]
        with patch("reports.ai.views.deepseek_client") as cliente:
            cliente.return_value.chat.side_effect = respuestas
            respuesta = self.client.post(
                reverse("reports:ai_chat"),
                data=json.dumps({"message": "Ayer el gasto de Meta en Bali fue 320.000"}),
                content_type="application/json",
            )

        self.assertIsNone(respuesta.json()["pending_entry"])


class PaisInferidoTests(CatalogosMixin, TestCase):
    """Si la marca vende en un solo pais, no se pregunta."""

    def setUp(self):
        self.crear()
        self.ec, _ = Country.objects.get_or_create(name="Ecuador", defaults={"code": "EC"})
        self.user = _staff("estefy")
        self.user.profile.business_units.set([self.bali])

    def test_con_un_solo_pais_no_lo_pregunta(self):
        # Bali vende solo en Colombia: preguntarlo todos los dias es ruido, y el ruido
        # entrena a la gente a contestar sin leer.
        self.bali.countries.set([self.co])

        plan = plan_entry(
            self.user, "gasto_publicitario", marca="Bali",
            plataforma="Meta Ads", fecha="ayer", monto="320000",
        )

        self.assertEqual(plan["fecha"], self.ayer.isoformat())
        self.assertIn("Colombia", plan["que"])

    def test_con_varios_paises_si_lo_pregunta(self):
        self.bali.countries.set([self.co, self.ec])

        with self.assertRaises(MissingData) as contexto:
            plan_entry(
                self.user, "gasto_publicitario", marca="Bali",
                plataforma="Meta Ads", fecha="ayer", monto="320000",
            )

        self.assertIn("Colombia", str(contexto.exception))
        self.assertIn("Ecuador", str(contexto.exception))

    def test_un_pais_que_la_marca_no_tiene_se_rechaza(self):
        self.bali.countries.set([self.co])

        with self.assertRaises(EntryError) as contexto:
            plan_entry(
                self.user, "gasto_publicitario", marca="Bali", pais="Ecuador",
                plataforma="Meta Ads", fecha="ayer", monto="320000",
            )

        self.assertIn("no tiene Ecuador", str(contexto.exception))


class SinLlaveDelGrupoTests(CatalogosMixin, TestCase):
    """Registrar los datos de mi propia marca no exige la llave del grupo.

    Antes si, y eso convertia cada persona nueva en una tarea manual. Los permisos de
    Django mas el alcance por marca son el control que corresponde.
    """

    def setUp(self):
        self.crear()
        self.bali.countries.set([self.co])
        self.user = _staff("nueva-persona", con_llave=False)
        self.user.profile.business_units.set([self.bali])
        self.client.force_login(self.user)

    @override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
    def test_sin_grupo_pero_con_permiso_si_registra(self):
        respuesta = self.client.post(
            reverse("reports:ai_data_entry_apply"),
            data=json.dumps({
                "confirm": True, "kind": "gasto_publicitario", "marca": "Bali",
                "plataforma": "Meta Ads", "fecha": "ayer", "monto": "320000",
            }),
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(DailyAdSpend.objects.exists())

    @override_settings(DEEPSEEK_API_KEY="clave-de-prueba")
    def test_sin_permiso_de_django_no_registra(self):
        sin_permiso = _staff("solo-lectura", con_llave=False, permisos=())
        sin_permiso.profile.business_units.set([self.bali])
        self.client.force_login(sin_permiso)

        respuesta = self.client.post(
            reverse("reports:ai_data_entry_apply"),
            data=json.dumps({
                "confirm": True, "kind": "gasto_publicitario", "marca": "Bali",
                "plataforma": "Meta Ads", "fecha": "ayer", "monto": "320000",
            }),
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertIn("no tiene permiso", respuesta.json()["detail"])
        self.assertFalse(DailyAdSpend.objects.exists())
