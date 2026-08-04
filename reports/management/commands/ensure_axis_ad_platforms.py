"""Deja completo el catalogo de plataformas de pauta.

Marketplace pauta dentro de Mercado Libre y de Falabella, y ninguna de las dos existia
como plataforma: Axis solo conocia Google Ads y Meta Ads. Sin ellas, Karen no podia
registrar "el gasto de Mercado Libre fue X" --el asistente respondia, con razon, que esa
plataforma no existe-- y el ROAS de Marketplace se calculaba contra una inversion de cero.

Idempotente: `get_or_create` sobre el slug.
"""
from django.core.management.base import BaseCommand

from reports.models import AdPlatform

PLATAFORMAS = (
    ("Mercado Libre Ads", "mercadolibre-ads"),
    ("Falabella Ads", "falabella-ads"),
)


class Command(BaseCommand):
    help = "Crea las plataformas de pauta de Marketplace si faltan."

    def handle(self, *args, **options):
        for nombre, slug in PLATAFORMAS:
            plataforma, creada = AdPlatform.objects.get_or_create(
                slug=slug, defaults={"name": nombre, "is_active": True}
            )
            if not creada and not plataforma.is_active:
                plataforma.is_active = True
                plataforma.save(update_fields=["is_active", "updated_at"])
                self.stdout.write(f"  {nombre}: reactivada")
            else:
                self.stdout.write(f"  {nombre}: {'creada' if creada else 'ya estaba'}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Plataformas activas: {', '.join(AdPlatform.objects.filter(is_active=True).values_list('name', flat=True))}"
            )
        )
