"""Quien puede dejar que la IA escriba.

Dos condiciones, las dos obligatorias:

**Estar en el grupo `IA Escritura`.** Es una llave explicita: alguien tiene que ponerte
ahi a mano. No se deduce del cargo ni de ser superusuario.

**Tener el permiso de Django del modelo que se va a tocar.** El grupo abre la puerta;
el permiso dice que se puede mover adentro. Sin esta segunda condicion el grupo seria un
atajo para saltarse los permisos que Axis ya tiene definidos.

Ojo con como se configuro el grupo: hoy carga los 216 permisos que existen, incluidos los
de borrado. Mientras solo tenga superusuarios adentro no cambia nada, porque ya los
tenian. El dia que entre alguien que no lo sea, ese grupo le da todo. La llave deberia
ir vacia de permisos y que cada quien traiga los suyos de su rol.
"""
from django.contrib.auth.models import Group

WRITE_GROUP = "IA Escritura"

# Permiso necesario segun lo que la accion vaya a escribir.
IMPORT_PERMISSIONS = ("reports.change_dailychannelsale", "reports.change_dailyproductcategorysale")


def in_write_group(user):
    return user.groups.filter(name=WRITE_GROUP).exists()


def write_group_exists():
    return Group.objects.filter(name=WRITE_GROUP).exists()


def can_import_data(user):
    """Si esta persona puede cargar datos desde un archivo."""
    return in_write_group(user) and all(user.has_perm(p) for p in IMPORT_PERMISSIONS)


def can_change_config(user):
    """Si esta persona puede aplicar cambios de configuracion.

    El permiso concreto lo revisa `apply_change` segun lo que se vaya a tocar: cambiar
    una marca y cambiar el semaforo no piden el mismo.
    """
    return in_write_group(user)


def why_not_config(user):
    if not write_group_exists():
        return f"El grupo '{WRITE_GROUP}' no existe todavia en este entorno."
    if not in_write_group(user):
        return (
            f"Solo quien este en el grupo '{WRITE_GROUP}' puede aplicar cambios de "
            "configuracion. Puedo validarte el cambio y mostrartelo, pero no aplicarlo."
        )
    return ""


def why_not_import(user):
    """El motivo, para decirselo a la persona en vez de un 403 pelado."""
    if not write_group_exists():
        return f"El grupo '{WRITE_GROUP}' no existe todavia en este entorno."
    if not in_write_group(user):
        return (
            f"Solo quien este en el grupo '{WRITE_GROUP}' puede cargar datos. "
            "Puedo revisar el archivo y mostrarte que cambiaria, pero no escribirlo."
        )
    faltantes = [p for p in IMPORT_PERMISSIONS if not user.has_perm(p)]
    if faltantes:
        return f"Estas en el grupo pero te faltan permisos de Django: {', '.join(faltantes)}."
    return ""
