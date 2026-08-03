"""Las muestras a creadoras UGC se registran, pero no son venta.

En la hoja de Ecuador hay 22 filas con CENTRO DE COSTOS = "Publicidad" y precio 0: son
productos que se envian a creadoras para que hagan contenido. El importador las
descartaba en silencio porque ese canal no existia, asi que las unidades entregadas no
quedaban en ninguna parte.

Meterlas como venta con importe 0 tampoco sirve: no mueven los ingresos, pero inflarian
"unidades vendidas" con producto regalado.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from reports.models import BusinessUnit, Channel, Country, DailyChannelSale, ProductCategory, DailyProductCategorySale
from reports.services.sales_dashboard import build_sales_snapshot

FILTROS = {"business_unit": "uva", "country": "EC", "date_start": "2026-07-01", "date_end": "2026-07-31"}


class CanalDeMuestrasTests(TestCase):
    def setUp(self):
        from reports.services.sales_dashboard import ensure_uva_catalogs

        ensure_uva_catalogs()

    def test_el_canal_existe_en_uva(self):
        canal = Channel.objects.filter(slug="ugc-muestras-uva").first()

        self.assertIsNotNone(canal)
        self.assertEqual(canal.business_unit.slug, "uva")
        self.assertEqual(canal.name, "Muestras UGC")
        self.assertTrue(canal.is_active)

    def test_el_importador_de_ecuador_reconoce_publicidad(self):
        from reports.management.commands.import_ecuador_sales import CHANNEL_BY_LABEL

        self.assertEqual(CHANNEL_BY_LABEL["publicidad"], "ugc-muestras-uva")

    def test_el_del_sync_diario_tambien(self):
        from reports.management.commands.fetch_onedrive_excel import channel_slug_for_row

        self.assertEqual(channel_slug_for_row("EC", "Publicidad", "x"), "ugc-muestras-uva")
        # Y no se confunde con los otros dos.
        self.assertEqual(channel_slug_for_row("EC", "Whatsapp", "x"), "whatsapp-uva-ec")
        self.assertEqual(channel_slug_for_row("EC", "Pagina", "x"), "ecommerce-uva")


class LasMuestrasNoSonVentaTests(TestCase):
    def setUp(self):
        from reports.services.sales_dashboard import ensure_uva_catalogs

        ensure_uva_catalogs()
        self.unidad = BusinessUnit.objects.get(slug="uva")
        self.pais, _ = Country.objects.get_or_create(code="EC", defaults={"name": "Ecuador"})
        self.web = Channel.objects.get(business_unit=self.unidad, slug="ecommerce-uva")
        self.muestras = Channel.objects.get(business_unit=self.unidad, slug="ugc-muestras-uva")

    def _venta(self, canal, monto, unidades):
        DailyChannelSale.objects.create(
            business_unit=self.unidad, country=self.pais, channel=canal,
            sale_date=date(2026, 7, 15), sales_amount=Decimal(monto),
            order_count=1 if monto else 0, units=unidades,
        )

    def test_las_unidades_regaladas_no_entran_a_unidades_vendidas(self):
        self._venta(self.web, "100000", 4)
        self._venta(self.muestras, "0", 6)

        kpis = build_sales_snapshot(dict(FILTROS))["kpis"]

        self.assertEqual(kpis["sales_total"], 100000.0)
        # 4, no 10: las 6 muestras se registran pero no se venden.
        self.assertEqual(kpis["units"], 4)

    def test_el_ticket_promedio_no_se_diluye_con_las_muestras(self):
        self._venta(self.web, "100000", 4)
        self._venta(self.muestras, "0", 6)

        kpis = build_sales_snapshot(dict(FILTROS))["kpis"]

        self.assertEqual(kpis["average_ticket"], 100000.0)

    def test_las_muestras_si_quedan_registradas(self):
        self._venta(self.muestras, "0", 6)

        fila = DailyChannelSale.objects.get(channel=self.muestras)
        self.assertEqual(fila.units, 6)
        self.assertEqual(fila.sales_amount, Decimal("0"))
