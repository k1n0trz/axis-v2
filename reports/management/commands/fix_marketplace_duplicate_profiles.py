"""Repunta los perfiles que quedaron apuntando al duplicado 'Marketplaces'.

La marca 'Marketplaces' se desactivo el 3-ago-2026 por ser un duplicado sin datos de la
real, 'Marketplace'. Lo que no se hizo entonces fue mover los perfiles que la tenian
asignada, y eso dejo a Karen viendo **solo** una marca muerta: para ella el asistente no
tenia datos de nada.

Idempotente: correrlo dos veces no cambia nada la segunda.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from reports.models import BusinessUnit

MUERTA = "marketplaces"
REAL = "marketplace"


class Command(BaseCommand):
    help = "Cambia la marca 'Marketplaces' por 'Marketplace' en los perfiles que la tengan."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        muerta = BusinessUnit.objects.filter(slug=MUERTA).first()
        if not muerta:
            self.stdout.write("No existe el duplicado: nada que hacer.")
            return
        try:
            real = BusinessUnit.objects.get(slug=REAL)
        except BusinessUnit.DoesNotExist:
            raise CommandError(f"No existe la marca '{REAL}'. No se toca nada.")

        afectados = list(User.objects.filter(profile__business_units=muerta).distinct())
        if not afectados:
            self.stdout.write("Ningun perfil apunta al duplicado.")
            return

        for usuario in afectados:
            perfil = usuario.profile
            antes = [b.name for b in perfil.business_units.all()]
            if options["dry_run"]:
                self.stdout.write(f"  {usuario.username}: {antes} -> quitaria '{muerta.name}'")
                continue
            perfil.business_units.add(real)
            perfil.business_units.remove(muerta)
            despues = [b.name for b in perfil.business_units.all()]
            self.stdout.write(f"  {usuario.username}: {antes} -> {despues}")

        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"{len(afectados)} perfiles repuntados."))
