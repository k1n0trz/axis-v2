"""Habilita a una persona para confirmar escrituras del asistente.

Son dos pasos y es facil olvidar el segundo: el grupo `IA Escritura` es la llave, y los
permisos de Django dicen que puede mover adentro. Meter a alguien solo al grupo lo deja
igual que antes --pasa el 403 y falla al aplicar-- asi que este comando hace los dos y
muestra el resultado.

    python manage.py grant_ai_write_access --user Karen
    python manage.py grant_ai_write_access --user Karen --business-unit marketplace
    python manage.py grant_ai_write_access --user Karen --revoke
"""
from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand, CommandError

from reports.ai.permissions import IMPORT_PERMISSIONS, WRITE_GROUP, can_import_data
from reports.models import BusinessUnit, UserProfile

# Registrar un dato hablando necesita el de inversion, que no esta en IMPORT_PERMISSIONS:
# Karen quedo habilitada para cargar archivos pero no para dictar un gasto, que es justo
# lo que ella hace todos los dias.
ENTRY_PERMISSIONS = ("reports.change_dailyadspend",)

# Los de importar mas los de configuracion: si alguien puede confirmar cargas, tambien
# necesita poder aplicar los cambios de configuracion que el asistente le proponga.
CONFIG_PERMISSIONS = (
    "reports.change_businessunit",
    "reports.change_country",
    "reports.change_channel",
    "reports.change_roastrafficlightsetting",
)


class Command(BaseCommand):
    help = "Da (o quita) a un usuario la llave y los permisos para confirmar escrituras de la IA."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True)
        parser.add_argument(
            "--business-unit",
            action="append",
            # `default=None` y no "": con action="append" argparse le hace .append() al
            # default, y sobre una cadena eso revienta.
            default=None,
            help="Slug de marca a asignar en el perfil. Se puede repetir.",
        )
        parser.add_argument(
            "--config",
            action="store_true",
            help="Incluye tambien los permisos de configuracion (marcas, paises, semaforo).",
        )
        parser.add_argument("--revoke", action="store_true", help="Retira la llave del grupo.")

    def handle(self, *args, **options):
        try:
            usuario = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"No existe el usuario '{options['user']}'.")

        grupo, creado = Group.objects.get_or_create(name=WRITE_GROUP)
        if creado:
            self.stdout.write(f"Grupo '{WRITE_GROUP}' creado (sin permisos, como debe ser).")
        if grupo.permissions.exists():
            # La llave tiene que ir vacia: los permisos los trae cada quien de su rol.
            self.stdout.write(
                self.style.WARNING(
                    f"OJO: el grupo '{WRITE_GROUP}' tiene {grupo.permissions.count()} permisos "
                    "adentro. Deberia ir vacio, o cualquiera que entre los hereda todos."
                )
            )

        if options["revoke"]:
            usuario.groups.remove(grupo)
            self.stdout.write(self.style.SUCCESS(f"{usuario.username} ya no puede confirmar escrituras."))
            return

        usuario.groups.add(grupo)
        rutas = (
            list(IMPORT_PERMISSIONS)
            + list(ENTRY_PERMISSIONS)
            + (list(CONFIG_PERMISSIONS) if options["config"] else [])
        )
        for ruta in rutas:
            codename = ruta.split(".")[-1]
            usuario.user_permissions.add(Permission.objects.get(codename=codename))

        marcas = [s for s in (options["business_unit"] or []) if s]
        if marcas:
            perfil, _ = UserProfile.objects.get_or_create(user=usuario)
            encontradas = list(BusinessUnit.objects.filter(slug__in=marcas, is_active=True))
            faltantes = set(marcas) - {b.slug for b in encontradas}
            if faltantes:
                raise CommandError(f"No hay marcas activas con estos slugs: {', '.join(sorted(faltantes))}.")
            perfil.business_units.set(encontradas)

        # Releido: los permisos se cachean en la instancia y `can_import_data` daria False.
        usuario = User.objects.get(pk=usuario.pk)
        perfil = getattr(usuario, "profile", None)
        self.stdout.write(self.style.SUCCESS(f"--- {usuario.username} ---"))
        self.stdout.write(f"  puede confirmar cargas: {can_import_data(usuario)}")
        self.stdout.write(f"  grupos: {[g.name for g in usuario.groups.all()]}")
        if perfil:
            self.stdout.write(f"  marcas: {[b.name for b in perfil.business_units.all()]}")
