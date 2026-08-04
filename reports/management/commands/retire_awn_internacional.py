"""Desactiva Awn Internacional: por ahora no se usa.

No borra nada. `AwnInternationalFollowerMetric` guarda meses de seguidores, visitas y
costo por seguidor; un delete se los llevaria y el dia que vuelvan a necesitarlo no habria
de donde sacarlo. Se apaga la bandera del modulo y, si existe, se desactiva su marca.

Reversible: `--activar` lo vuelve a encender.
"""
from django.core.management.base import BaseCommand

from reports.models import BusinessUnit


class Command(BaseCommand):
    help = "Desactiva (o reactiva) el modulo de Awn Internacional sin borrar sus datos."

    def add_arguments(self, parser):
        parser.add_argument("--activar", action="store_true")

    def handle(self, *args, **options):
        activo = bool(options["activar"])
        from reports.models import AwnInternationalFollowerMetric

        filas = AwnInternationalFollowerMetric.objects.count()
        marcas = BusinessUnit.objects.filter(slug__icontains="awn")
        for marca in marcas:
            marca.is_active = activo
            marca.save(update_fields=["is_active", "updated_at"])
            self.stdout.write(f"  marca '{marca.name}': is_active={activo}")

        if not marcas:
            self.stdout.write("  no hay marca 'awn' en el catalogo (nada que desactivar ahi)")

        self.stdout.write(
            self.style.SUCCESS(
                f"Awn Internacional {'activada' if activo else 'desactivada'}. "
                f"Sus {filas} filas de seguidores siguen en la base: no se borro nada, "
                "y la ruta se apaga con FEATURE_AWN_ENABLED en el entorno."
            )
        )
