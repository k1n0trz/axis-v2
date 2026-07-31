"""Siembra los catalogos base: unidades, paises, canales y plataformas.

Esto vivia dentro del render: /bali/, /marketplace/, /ad-spend/ y /web-sales/
llamaban a `ensure_*_catalogs()` en cada GET, y como esas funciones usan
`update_or_create`, cada carga de pagina hacia entre 4 y 10 escrituras y hasta 6
transacciones contra Cloud SQL. Tambien reescribia `updated_at` de unidades y
canales con cada visita, y hacia imposible servir la app desde una replica de
lectura.

Es idempotente, asi que se puede correr en cada despliegue. No va en una
migracion a proposito: sembrar catalogos al construir la base de pruebas rompe
las docenas de tests que crean sus propias unidades y canales.
"""
from django.core.management.base import BaseCommand

from reports.services.sales_dashboard import (
    ensure_ad_platform_catalogs,
    ensure_bali_catalogs,
    ensure_marketplace_catalogs,
    ensure_uva_catalogs,
)


class Command(BaseCommand):
    help = "Crea o actualiza los catalogos base de Axis (unidades, paises, canales, plataformas)."

    def handle(self, *args, **options):
        ensure_uva_catalogs()
        ensure_bali_catalogs()
        ensure_marketplace_catalogs()
        platforms = ensure_ad_platform_catalogs()
        self.stdout.write(self.style.SUCCESS(f"Catalogos listos. Plataformas de pauta: {', '.join(sorted(platforms))}."))
