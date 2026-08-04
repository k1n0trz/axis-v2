"""Cambios de configuracion que la IA puede proponer y una persona confirma.

Que entra aqui y que no:

**Entra lo que vive en la base.** Marcas, paises, canales y los umbrales del semaforo de
ROAS son filas: se pueden cambiar sin desplegar. La lista es blanca y explicita, campo
por campo. Lo que no este en `EDITABLE` no se puede tocar por este camino, aunque el
modelo lo pida con mucha seguridad.

**No entra lo que vive en el codigo.** Los colores del tablero estan en las plantillas,
no en un campo: cambiarlos es un cambio de codigo y va por otro camino. Decirle a alguien
"listo, ya cambie los colores" cuando en realidad no hay donde guardarlos seria peor que
decirle que no se puede.

**Nada se borra.** Una marca se desactiva, no se elimina: sus ventas historicas siguen
colgando de ella. `is_active=False` la saca del tablero y es reversible; un delete se
llevaria anos de datos por delante.

Igual que con los archivos: la IA propone y simula, el boton lo aprieta una persona.
"""
from decimal import Decimal, InvalidOperation

from ..models import BusinessUnit, Channel, Country, RoasTrafficLightSetting


class ConfigError(ValueError):
    """El cambio pedido no se puede hacer. El mensaje se le muestra a la persona."""


def _boolean(valor):
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in {"true", "si", "sí", "1", "activa", "activo"}:
        return True
    if texto in {"false", "no", "0", "inactiva", "inactivo"}:
        return False
    raise ConfigError(f"'{valor}' no es un si/no valido.")


def _entero(valor):
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ConfigError(f"'{valor}' no es un numero entero.")
    if numero < 0:
        raise ConfigError("El orden no puede ser negativo.")
    return numero


def _decimal(valor):
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (TypeError, InvalidOperation):
        raise ConfigError(f"'{valor}' no es un numero.")
    if numero < 0:
        raise ConfigError("El umbral no puede ser negativo.")
    return numero


def _texto(valor):
    limpio = str(valor or "").strip()
    if len(limpio) < 2:
        raise ConfigError("El nombre es demasiado corto.")
    return limpio[:120]


# Lista blanca. Cada entrada: modelo, campo permitido, como se convierte el valor, y el
# permiso de Django que hace falta. Sin `slug`: cambiarlo rompe los importadores, que
# eligen la marca por slug.
EDITABLE = {
    "marca": {
        "model": BusinessUnit,
        "label": "Marca",
        "permission": "reports.change_businessunit",
        "fields": {
            "nombre": ("name", _texto),
            "orden": ("display_order", _entero),
            "activa": ("is_active", _boolean),
        },
    },
    "pais": {
        "model": Country,
        "label": "Pais",
        "permission": "reports.change_country",
        "fields": {
            "nombre": ("name", _texto),
            "orden": ("display_order", _entero),
            "activo": ("is_active", _boolean),
        },
    },
    "canal": {
        "model": Channel,
        "label": "Canal",
        "permission": "reports.change_channel",
        "fields": {
            "nombre": ("name", _texto),
            "activo": ("is_active", _boolean),
        },
    },
    "semaforo_roas": {
        "model": RoasTrafficLightSetting,
        "label": "Semaforo de ROAS",
        "permission": "reports.change_roastrafficlightsetting",
        "fields": {
            "verde_desde": ("green_min", _decimal),
            "amarillo_desde": ("yellow_min", _decimal),
        },
    },
}


def describe_config(user):
    """Lo que hoy se puede cambiar sin desplegar codigo."""
    return {
        "marcas": [
            {"nombre": b.name, "orden": b.display_order, "activa": b.is_active}
            for b in BusinessUnit.objects.order_by("display_order", "name")
        ],
        "paises": [
            {"nombre": c.name, "codigo": c.code, "orden": c.display_order, "activo": c.is_active}
            for c in Country.objects.order_by("display_order", "name")
        ],
        "canales": [
            {"nombre": c.name, "activo": c.is_active} for c in Channel.objects.order_by("name")
        ],
        "semaforo_roas": [
            {"nombre": s.name, "verde_desde": float(s.green_min), "amarillo_desde": float(s.yellow_min)}
            for s in RoasTrafficLightSetting.objects.filter(is_active=True)
        ],
        "campos_editables": {
            clave: sorted(spec["fields"]) for clave, spec in EDITABLE.items()
        },
        "nota": (
            "Solo se editan los que ya existen: crear una marca o un pais nuevo no se "
            "puede por aqui, y borrar tampoco --lo mas cercano es desactivar. "
            "Los colores y los tipos de grafico NO estan aca: viven en las plantillas, "
            "asi que cambiarlos es un cambio de codigo, no de configuracion."
        ),
    }


def _find(spec, nombre):
    modelo = spec["model"]
    objeto = modelo.objects.filter(name__iexact=str(nombre).strip()).first()
    if objeto:
        return objeto
    if hasattr(modelo, "slug"):
        objeto = modelo.objects.filter(slug__iexact=str(nombre).strip()).first()
    if not objeto and modelo is RoasTrafficLightSetting:
        objeto = modelo.objects.filter(is_active=True).first()
    if not objeto:
        existentes = ", ".join(modelo.objects.values_list("name", flat=True)[:12])
        raise ConfigError(f"No encuentro '{nombre}'. Los que hay: {existentes}.")
    return objeto


def plan_change(user, target, name, field, value):
    """Valida el cambio y devuelve antes/despues. No escribe nada."""
    spec = EDITABLE.get(str(target).strip().lower())
    if not spec:
        raise ConfigError(
            f"'{target}' no se puede cambiar por aqui. Se puede: {', '.join(EDITABLE)}."
        )
    campo = spec["fields"].get(str(field).strip().lower())
    if not campo:
        raise ConfigError(
            f"En {spec['label'].lower()} solo se puede cambiar: {', '.join(spec['fields'])}."
        )

    atributo, convertir = campo
    objeto = _find(spec, name)
    nuevo = convertir(value)
    anterior = getattr(objeto, atributo)

    if str(anterior) == str(nuevo):
        raise ConfigError(f"Ya esta en '{nuevo}': no hay nada que cambiar.")

    return {
        "target": str(target).strip().lower(),
        "tipo": spec["label"],
        "objeto": str(objeto),
        "objeto_id": objeto.pk,
        "campo": str(field).strip().lower(),
        "antes": str(anterior),
        "despues": str(nuevo),
        "permiso": spec["permission"],
        "aviso": _aviso(spec, atributo, nuevo, objeto),
    }


def _aviso(spec, atributo, nuevo, objeto):
    """Lo que la persona tiene que saber antes de confirmar."""
    if atributo == "is_active" and nuevo is False:
        return (
            f"Esto saca '{objeto}' del tablero. Sus datos historicos no se borran y se "
            "puede volver a activar."
        )
    if spec["model"] is RoasTrafficLightSetting:
        return (
            "Cambia el color del semaforo en todo el tablero. Verde debe quedar por "
            "encima de amarillo o la base lo rechaza."
        )
    return ""


def apply_change(user, target, name, field, value):
    """Aplica el cambio y deja constancia. Solo se llama tras confirmacion humana."""
    from ..integrations.run_log import track_run
    from ..models import AiConfigChange

    plan = plan_change(user, target, name, field, value)
    if not user.has_perm(plan["permiso"]):
        raise ConfigError(f"Te falta el permiso {plan['permiso']}.")

    spec = EDITABLE[plan["target"]]
    atributo, convertir = spec["fields"][plan["campo"]]
    objeto = spec["model"].objects.get(pk=plan["objeto_id"])
    setattr(objeto, atributo, convertir(value))
    # full_clean para que las restricciones del modelo se apliquen antes de guardar:
    # el semaforo tiene una que exige amarillo <= verde.
    objeto.full_clean()
    objeto.save()

    with track_run(
        "IA configuracion", command=f"{plan['target']}.{plan['campo']} (via asistente, {user.get_username()})"
    ) as run:
        run.summary = f"{plan['objeto']}: {plan['campo']} {plan['antes']} -> {plan['despues']}"

    AiConfigChange.objects.create(
        user=user,
        target=plan["target"],
        object_label=plan["objeto"],
        field=plan["campo"],
        old_value=plan["antes"],
        new_value=plan["despues"],
    )
    return {**plan, "aplicado": True, "nota": "Este cambio SI quedo aplicado."}
