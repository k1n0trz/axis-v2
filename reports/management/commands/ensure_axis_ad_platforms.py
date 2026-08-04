"""Deja completo el catalogo de plataformas de pauta.

Marketplace pauta dentro de Mercadolibre, Falabella, Rappi y Farmatodo, y ninguna existia
como plataforma: Axis solo conocia Google Ads y Meta Ads. Sin ellas, Karen no podia
registrar "el gasto de Mercado Libre fue X" --el asistente respondia, con razon, que esa
plataforma no existe-- y el ROAS de Marketplace se calculaba contra una inversion de cero.

Idempotente: `get_or_create` sobre el slug.
"""
from django.core.management.base import BaseCommand

from reports.models import AdPlatform

# El nombre va **igual que el canal** en Axis, no "bonito": la plantilla del admin dice
# `Mercadolibre` sin espacio, y Karen dice "el gasto de Mercadolibre". Llamarla "Mercado
# Libre Ads" hacia que ni el archivo ni el dictado la encontraran. El slug lleva `-ads`
# para que en el codigo se distinga del canal del mismo nombre.
PLATAFORMAS = (
    ("Mercadolibre", "mercadolibre-ads"),
    ("Falabella", "falabella-ads"),
    ("Rappi", "rappi-ads"),
    ("Farmatodo", "farmatodo-ads"),
)


class Command(BaseCommand):
    help = "Crea las plataformas de pauta de Marketplace si faltan."

    def handle(self, *args, **options):
        for nombre, slug in PLATAFORMAS:
            plataforma, creada = AdPlatform.objects.get_or_create(
                slug=slug, defaults={"name": nombre, "is_active": True}
            )
            if creada:
                self.stdout.write(f"  {nombre}: creada")
                continue
            # `get_or_create` encuentra por slug y no corrige el nombre. La primera version
            # las creo como "Mercado Libre Ads" y ni el archivo ni el dictado las
            # encontraban: hay que renombrarlas, no solo dejarlas pasar.
            cambios = []
            if plataforma.name != nombre:
                cambios.append(f"'{plataforma.name}' -> '{nombre}'")
                plataforma.name = nombre
            if not plataforma.is_active:
                cambios.append("reactivada")
                plataforma.is_active = True
            if cambios:
                plataforma.save(update_fields=["name", "is_active", "updated_at"])
                self.stdout.write(f"  {nombre}: {', '.join(cambios)}")
            else:
                self.stdout.write(f"  {nombre}: ya estaba")
        self.stdout.write(
            self.style.SUCCESS(
                f"Plataformas activas: {', '.join(AdPlatform.objects.filter(is_active=True).values_list('name', flat=True))}"
            )
        )
