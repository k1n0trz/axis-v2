"""DistriSex como marca propia.

Es la operacion mayorista: catalogo de Bali y Uva juntos, tienda WooCommerce
propia (distrisexcolombia.com) y facturacion en COP. La migracion 0023 habia
borrado la unidad; la 0056 la vuelve a crear porque ya tiene datos reales.

Regresion cubierta: `sales_web` se calculaba con `slug == "ecommerce-uva"`
escrito a mano en seis lugares, asi que las ventas de DistriSex entraban al
total pero salian en cero en el desglose web.
"""
import json
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from reports.models import BusinessUnit, Channel, Country, DailyChannelSale, DailyProductCategorySale
from reports.services.sales_dashboard import build_sales_snapshot

FILTROS = {"business_unit": "distrisex", "country": "CO", "date_start": "2026-07-24", "date_end": "2026-07-29"}


class MarcaDistrisexTests(TestCase):
    def test_la_migracion_deja_la_marca_lista(self):
        unidad = BusinessUnit.objects.get(slug="distrisex")

        self.assertTrue(unidad.is_active)
        self.assertEqual(unidad.name, "DistriSex")
        self.assertIn("CO", [pais.code for pais in unidad.countries.all()])
        self.assertEqual(
            sorted(Channel.objects.filter(business_unit=unidad).values_list("slug", flat=True)),
            ["ecommerce-distrisex", "whatsapp-distrisex"],
        )


class DesgloseWebDistrisexTests(TestCase):
    def setUp(self):
        self.unidad = BusinessUnit.objects.get(slug="distrisex")
        self.pais = Country.objects.get(code="CO")
        self.canal = Channel.objects.get(business_unit=self.unidad, slug="ecommerce-distrisex")

    def _venta(self, dia, monto, pedidos, unidades):
        return DailyChannelSale.objects.create(
            business_unit=self.unidad,
            country=self.pais,
            channel=self.canal,
            sale_date=dia,
            sales_amount=Decimal(monto),
            order_count=pedidos,
            units=unidades,
            source_file="woocommerce-api",
        )

    def test_la_venta_mayorista_cuenta_como_venta_web(self):
        self._venta(date(2026, 7, 28), "101444518", 80, 3116)
        self._venta(date(2026, 7, 29), "105967985", 80, 4002)

        kpis = build_sales_snapshot(dict(FILTROS))["kpis"]

        self.assertEqual(kpis["sales_total"], 207412503.0)
        # Antes daba 0: el desglose solo reconocia el canal de Uva.
        self.assertEqual(kpis["sales_web"], 207412503.0)
        self.assertEqual(kpis["orders"], 160)
        self.assertEqual(kpis["units"], 7118)

    def test_el_canal_webcam_de_bali_no_se_cuela_como_web(self):
        bali, _ = BusinessUnit.objects.get_or_create(slug="bali", defaults={"name": "Bali"})
        webcam, _ = Channel.objects.get_or_create(
            business_unit=bali, slug="bali-community-webcam", defaults={"name": "Comunidad Webcam"}
        )
        DailyChannelSale.objects.create(
            business_unit=bali,
            country=self.pais,
            channel=webcam,
            sale_date=date(2026, 7, 28),
            sales_amount=Decimal("500000"),
            order_count=5,
            units=5,
        )

        kpis = build_sales_snapshot({**FILTROS, "business_unit": "bali"})["kpis"]

        self.assertEqual(kpis["sales_total"], 500000.0)
        self.assertEqual(kpis["sales_web"], 0.0)


@override_settings(
    WOOCOMMERCE_DISTRISEX_BASE_URL="https://distrisexcolombia.com",
    WOOCOMMERCE_DISTRISEX_CONSUMER_KEY="ck_prueba",
    WOOCOMMERCE_DISTRISEX_CONSUMER_SECRET="cs_prueba",
)
class ImportacionDistrisexTests(TestCase):
    PEDIDOS = [
        {
            "id": 1,
            "total": "160390",
            "shipping_total": "10000",
            "line_items": [
                {"name": "Potencializador Nitroxs Caja x 20 sobres", "quantity": 3, "total": "150390", "subtotal": "150390"},
            ],
        }
    ]

    def _correr(self, *extra):
        salida = StringIO()
        with patch("reports.management.commands.fetch_woocommerce_sales.WooCommerceClient") as cliente:
            cliente.return_value.iter_orders_for_day.return_value = self.PEDIDOS
            cliente.return_value.get_sales_report_for_day.return_value = {}
            call_command(
                "fetch_woocommerce_sales",
                "--date=2026-07-29",
                "--country=CO",
                "--store=DISTRISEX",
                "--business-unit=distrisex",
                "--channel-slug=ecommerce-distrisex",
                *extra,
                stdout=salida,
            )
        return salida.getvalue(), cliente

    def test_store_elige_las_credenciales_de_la_tienda_no_las_del_pais(self):
        _, cliente = self._correr("--skip-category-sales")

        args = cliente.call_args.args
        self.assertEqual(args[0], "https://distrisexcolombia.com")
        self.assertEqual(args[1], "ck_prueba")
        self.assertEqual(args[2], "cs_prueba")

    def test_skip_category_sales_guarda_solo_el_total_del_canal(self):
        salida, _ = self._correr("--skip-category-sales", "--sync-axis")

        self.assertEqual(json.loads(salida)["category_sales"], [])
        self.assertEqual(DailyChannelSale.objects.filter(business_unit__slug="distrisex").count(), 1)
        self.assertEqual(DailyProductCategorySale.objects.filter(business_unit__slug="distrisex").count(), 0)

    def test_sin_mapa_cada_producto_seria_su_propia_categoria(self):
        # Justifica --skip-category-sales: el catalogo mayorista genera cientos
        # de categorias basura por dia si se persisten sin mapa.
        salida, _ = self._correr()

        self.assertIn("potencializador-nitroxs", salida)

    def test_una_marca_que_no_es_uva_no_recibe_el_cajon_otros_uva(self):
        salida, _ = self._correr()

        self.assertNotIn("otros-uva", salida)


@override_settings(
    GOOGLE_ADS_CO_CUSTOMER_ID="7015245415",
    GOOGLE_ADS_EC_CUSTOMER_ID="6385600284",
    GOOGLE_ADS_BALI_CUSTOMER_ID="4042093126",
    GOOGLE_ADS_DISTRISEX_CUSTOMER_ID="9891336542",
)
class CuentaDeGoogleAdsPorMarcaTests(TestCase):
    """La cuenta de Google Ads se resuelve por marca antes que por pais.

    Uva tiene una cuenta por pais, pero Bali y DistriSex tienen una sola cada una.
    Antes Bali era un caso especial escrito a mano y cualquier marca nueva caia en
    la cuenta del pais, que es de Uva: DistriSex habria importado la pauta de
    UVA CUP COL como propia.
    """

    def setUp(self):
        from reports.management.commands.fetch_google_ads import Command

        self.resolver = Command()._default_customer_id

    def test_cada_marca_cae_en_su_cuenta(self):
        self.assertEqual(self.resolver("distrisex", "CO"), "9891336542")
        self.assertEqual(self.resolver("bali", "CO"), "4042093126")

    def test_uva_sigue_resolviendo_por_pais(self):
        self.assertEqual(self.resolver("uva", "CO"), "7015245415")
        self.assertEqual(self.resolver("uva", "EC"), "6385600284")

    def test_una_marca_sin_cuenta_propia_no_hereda_la_de_uva(self):
        # Laboratorio Helti existe en el MCC pero no esta modelada en Axis. Si
        # algun dia entra, no debe heredar la cuenta de Uva Colombia en silencio.
        with self.settings(GOOGLE_ADS_CO_CUSTOMER_ID=""):
            self.assertEqual(self.resolver("laboratorio-helti", "CO"), "")


@override_settings(
    GOOGLE_ADS_DEVELOPER_TOKEN="token",
    GOOGLE_ADS_CLIENT_ID="id",
    GOOGLE_ADS_CLIENT_SECRET="secreto",
    GOOGLE_ADS_REFRESH_TOKEN="refresh",
    GOOGLE_ADS_LOGIN_CUSTOMER_ID="1541318288",
    GOOGLE_ADS_DISTRISEX_CUSTOMER_ID="9891336542",
    GOOGLE_ADS_CO_CUSTOMER_ID="7015245415",
)
class PautaDistrisexTests(TestCase):
    """La pauta de una marca no debe caer en Uva.

    `_build_uva_payload` escribia `business_unit_slug="uva"` a mano, asi que el
    gasto de DistriSex se habria guardado como gasto de Uva. Y el total de la
    cuenta solo sumaba campanas con categoria asignada: DistriSex no tiene mapa de
    categorias, asi que habria reportado cero.
    """

    CAMPANAS = [
        {
            "results": [
                {
                    "campaign": {"id": "1", "name": "26/01/26 | Formularios | Mayoristas | Co"},
                    "customer": {"currencyCode": "COP"},
                    "metrics": {"costMicros": "30000000000", "conversions": "12"},
                },
                {
                    "campaign": {"id": "2", "name": "26/05/26 | Ventas | Search | Antioquia"},
                    "customer": {"currencyCode": "COP"},
                    "metrics": {"costMicros": "19806000000", "conversions": "8"},
                },
            ]
        }
    ]

    def _correr(self, *extra):
        salida = StringIO()
        with patch("reports.management.commands.fetch_google_ads.GoogleAdsClient") as cliente:
            cliente.return_value.search.return_value = self.CAMPANAS
            call_command(
                "fetch_google_ads",
                "--date=2026-07-29",
                "--country=CO",
                "--business-unit=distrisex",
                "--skip-geo",
                *extra,
                stdout=salida,
            )
        return json.loads(salida.getvalue()), cliente

    def test_el_gasto_queda_en_distrisex_no_en_uva(self):
        salida, _ = self._correr("--count-unmapped-spend")

        self.assertEqual(salida["daily_spend"]["business_unit_slug"], "distrisex")

    def test_usa_la_cuenta_de_distrisex_via_el_mcc(self):
        _, cliente = self._correr("--count-unmapped-spend")

        self.assertEqual(cliente.call_args.kwargs["login_customer_id"], "1541318288")
        self.assertEqual(cliente.return_value.search.call_args.args[0], "9891336542")

    def test_sin_mapa_de_categorias_el_total_igual_cuenta(self):
        salida, _ = self._correr("--count-unmapped-spend")

        self.assertEqual(salida["daily_spend"]["spend_amount"], "49806")
        self.assertEqual(salida["category_metrics"], [])
        self.assertIn("Campanas sin categoria incluidas", salida["daily_spend"]["notes"])

    def test_sin_la_bandera_el_total_sale_en_cero(self):
        # Comportamiento historico de Uva, conservado a proposito: cambiarlo por
        # defecto moveria cifras ya reportadas.
        salida, _ = self._correr()

        self.assertEqual(salida["daily_spend"]["spend_amount"], "0")
