"""La plantilla del admin, leida como N entradas de datos.

No hay importador nuevo: cada fila pasa por el mismo `plan_entry` que el chat, asi que un
archivo no puede escribir lo que un dictado no podria.
"""
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook

from reports.ai.data_entry import EntryError, apply_workbook, plan_workbook
from reports.models import (
    AdPlatform,
    BusinessUnit,
    Channel,
    Country,
    DailyAdSpend,
    DailyChannelSale,
    UserProfile,
)

CABECERA = ("Fecha", "Pais", "Canal", "Ventas", "Inversion", "Pedidos", "Unidades", "Notas")


def _staff(username="karen", permisos=("change_dailyadspend", "change_dailychannelsale")):
    usuario = User.objects.create_user(username=username, password="x", is_staff=True)
    UserProfile.objects.update_or_create(user=usuario, defaults={})
    for codename in permisos:
        usuario.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=usuario.pk)


def _plantilla(filas, cabecera=CABECERA):
    libro = Workbook()
    pagina = libro.active
    pagina.title = "Ventas Marketplace"
    pagina.append(list(cabecera))
    for fila in filas:
        pagina.append(list(fila))
    ruta = Path(tempfile.mkdtemp(prefix="axis-plantilla-")) / "plantilla.xlsx"
    libro.save(ruta)
    return str(ruta)


class LeerLaPlantillaTests(TestCase):
    def setUp(self):
        self.marketplace, _ = BusinessUnit.objects.get_or_create(
            name="Marketplace", defaults={"slug": "marketplace"}
        )
        self.co, _ = Country.objects.get_or_create(name="Colombia", defaults={"code": "CO"})
        self.marketplace.countries.set([self.co])
        self.meli_canal, _ = Channel.objects.get_or_create(
            name="Mercadolibre", defaults={"slug": "mercadolibre"}
        )
        # El nombre de la plataforma va igual que el canal: la plantilla dice
        # "Mercadolibre" y con "Mercado Libre Ads" no coincidia ninguno de los dos.
        self.meli_pauta, _ = AdPlatform.objects.get_or_create(
            slug="mercadolibre-ads", defaults={"name": "Mercadolibre"}
        )
        self.ayer = timezone.localdate() - timedelta(days=1)
        self.user = _staff()
        self.user.profile.business_units.set([self.marketplace])

    def test_una_fila_con_ventas_e_inversion_genera_dos_planes(self):
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 532660, 35745, 7, 7, ""),
        ])

        revision = plan_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(len(revision["planes"]), 2)
        self.assertEqual(revision["problemas"], [])

    def test_las_celdas_en_cero_no_generan_dato(self):
        # La plantilla trae las dos columnas siempre; escribir ceros borraria lo que haya.
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 455300, 0, 1, 2, ""),
        ])

        revision = plan_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(len(revision["planes"]), 1)
        self.assertEqual(revision["planes"][0]["tipo"], "ventas_de_canal")

    def test_la_fecha_de_excel_se_lee_como_fecha(self):
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 100000, 0, 1, 1, ""),
        ])

        revision = plan_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(revision["planes"][0]["fecha"], self.ayer.isoformat())

    def test_una_hoja_con_otra_forma_se_rechaza(self):
        ruta = _plantilla([("x", "y", "z")], cabecera=("Alfa", "Beta", "Gamma"))

        with self.assertRaises(EntryError) as contexto:
            plan_workbook(self.user, ruta, "Marketplace")

        self.assertIn("no tiene la forma de la plantilla", str(contexto.exception))

    def test_una_fila_mala_se_reporta_y_las_buenas_siguen(self):
        # Los importadores avisan, no corrigen: una fila rara no tumba el archivo.
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 100000, 0, 1, 1, ""),
            ("fecha rara", "Colombia", "Mercadolibre", 200000, 0, 1, 1, ""),
        ])

        revision = plan_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(len(revision["planes"]), 1)
        self.assertEqual(len(revision["problemas"]), 1)
        self.assertEqual(revision["problemas"][0]["fila"], 3)

    def test_las_filas_vacias_se_saltan(self):
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 100000, 0, 1, 1, ""),
            (None, None, None, None, None, None, None, None),
        ])

        revision = plan_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(len(revision["planes"]), 1)

    def test_no_se_puede_cargar_una_marca_que_no_ve(self):
        uva, _ = BusinessUnit.objects.get_or_create(name="Uva", defaults={"slug": "uva"})
        uva.countries.set([self.co])
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 100000, 0, 1, 1, ""),
        ])

        revision = plan_workbook(self.user, ruta, "Uva")

        self.assertEqual(revision["planes"], [])
        self.assertIn("no esta entre las marcas", revision["problemas"][0]["error"])

    def test_revisar_no_escribe_nada(self):
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 532660, 35745, 7, 7, ""),
        ])

        plan_workbook(self.user, ruta, "Marketplace")

        self.assertFalse(DailyChannelSale.objects.exists())
        self.assertFalse(DailyAdSpend.objects.exists())


class RegistrarLaPlantillaTests(LeerLaPlantillaTests):
    def test_aplicar_escribe_ventas_e_inversion(self):
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 532660, 35745, 7, 7, ""),
        ])

        resultado = apply_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(resultado["aplicados"], 2)
        self.assertEqual(DailyChannelSale.objects.get().sales_amount, Decimal("532660"))
        self.assertEqual(DailyAdSpend.objects.get().spend_amount, Decimal("35745"))

    def test_aplicar_dos_veces_corrige_y_no_duplica(self):
        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 100000, 0, 1, 1, ""),
        ])

        apply_workbook(self.user, ruta, "Marketplace")
        apply_workbook(self.user, ruta, "Marketplace")

        self.assertEqual(DailyChannelSale.objects.count(), 1)

    def test_queda_en_la_bitacora_con_el_conteo(self):
        from reports.models import IntegrationRun

        ruta = _plantilla([
            (datetime(self.ayer.year, self.ayer.month, self.ayer.day), "Colombia",
             "Mercadolibre", 100000, 0, 1, 1, ""),
        ])

        apply_workbook(self.user, ruta, "Marketplace")

        corrida = IntegrationRun.objects.filter(source="IA plantilla").first()
        self.assertIsNotNone(corrida)
        self.assertIn("1 filas registradas", corrida.summary)


class CatalogoDePlataformasTests(TestCase):
    """`ensure_axis_ad_platforms` tambien corrige nombres, no solo crea."""

    def _correr(self):
        from io import StringIO

        from django.core.management import call_command

        salida = StringIO()
        call_command("ensure_axis_ad_platforms", stdout=salida)
        return salida.getvalue()

    def test_crea_las_plataformas_de_marketplace(self):
        self._correr()

        activas = set(AdPlatform.objects.filter(is_active=True).values_list("name", flat=True))
        self.assertTrue({"Mercadolibre", "Falabella", "Rappi", "Farmatodo"}.issubset(activas))

    def test_renombra_una_plataforma_con_el_nombre_viejo(self):
        # get_or_create encuentra por slug y no corrige el nombre: la primera version las
        # dejo como "Mercado Libre Ads" y asi no las encontraba ni el archivo ni el chat.
        AdPlatform.objects.create(name="Mercado Libre Ads", slug="mercadolibre-ads")

        salida = self._correr()

        self.assertEqual(AdPlatform.objects.get(slug="mercadolibre-ads").name, "Mercadolibre")
        self.assertIn("-> 'Mercadolibre'", salida)

    def test_reactiva_una_plataforma_desactivada(self):
        AdPlatform.objects.create(name="Rappi", slug="rappi-ads", is_active=False)

        self._correr()

        self.assertTrue(AdPlatform.objects.get(slug="rappi-ads").is_active)

    def test_correrlo_dos_veces_no_cambia_nada_la_segunda(self):
        self._correr()

        salida = self._correr()

        self.assertNotIn("->", salida)
