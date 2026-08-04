"""Registrar un dato hablando, sin archivo.

Esto es lo que faltaba. Las Etapas G y H asumieron que actualizar datos era subir un
Excel, y para la mayoria de la gente no lo es: es decir "ayer el gasto de Meta en Bali
fue de 320.000" y que quede. El archivo es un camino, no el camino.

Como funciona, igual que todo lo que escribe en Axis:

**Lista blanca por tipo de dato.** Cada entrada declara en que tabla escribe, cual es su
clave unica real, que campos pide y que permiso hace falta. Lo que no este aqui no se
puede registrar por este camino.

**Acotado a las marcas de la persona.** Karen ve Marketplace: puede registrar gasto de
Marketplace y nada mas. La misma regla que las lecturas y que la carga de archivos.

**Si falta un dato, se pregunta.** `plan_entry` no rellena huecos con supuestos: devuelve
que falta y el modelo lo pide. Un asistente que adivina la fecha o el pais escribe en el
dia equivocado y nadie se entera hasta el cierre de mes.

**Si ya habia un valor, se muestra.** `update_or_create` sobre la clave unica es lo
correcto --volver a registrar el mismo dia corrige, no duplica-- pero pisar 400.000 con
320.000 sin que nadie lo vea seria peor que duplicar. El plan trae el antes.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from ..models import AdPlatform, BusinessUnit, Channel, Country, DailyAdSpend, DailyChannelSale
from ..services.common import normalize_text


class EntryError(ValueError):
    """No se puede registrar. El mensaje se le muestra a la persona."""


class MissingData(EntryError):
    """Falta un dato para poder registrar. El modelo tiene que preguntarlo."""


def _amount(valor, campo):
    try:
        numero = Decimal(str(valor).strip().replace(".", "").replace(",", "."))
    except (TypeError, InvalidOperation):
        raise EntryError(f"'{valor}' no es un monto que pueda leer para {campo}.")
    if numero < 0:
        raise EntryError(f"{campo} no puede ser negativo.")
    return numero


def _count(valor, campo):
    try:
        numero = int(Decimal(str(valor).strip()))
    except (TypeError, InvalidOperation, ValueError):
        raise EntryError(f"'{valor}' no es un numero entero para {campo}.")
    if numero < 0:
        raise EntryError(f"{campo} no puede ser negativo.")
    return numero


def _day(valor):
    """La fecha, sin adivinar. 'ayer' y 'hoy' se aceptan porque son inequivocos."""
    texto = normalize_text(valor)
    hoy = timezone.localdate()
    if texto in {"hoy", "today"}:
        return hoy
    if texto in {"ayer", "yesterday"}:
        return hoy - timedelta(days=1)
    if texto in {"antier", "anteayer"}:
        return hoy - timedelta(days=2)
    try:
        dia = date.fromisoformat(str(valor).strip())
    except (TypeError, ValueError):
        raise MissingData(
            f"No entiendo la fecha '{valor}'. Preguntale el dia exacto (AAAA-MM-DD)."
        )
    if dia > hoy:
        raise EntryError(f"{dia.isoformat()} es en el futuro: no se puede registrar todavia.")
    return dia


def _resolve(modelo, nombre, etiqueta, activos=True):
    consulta = modelo.objects.filter(is_active=True) if activos else modelo.objects.all()
    pedido = normalize_text(nombre)
    if not pedido:
        raise MissingData(f"Falta el {etiqueta}. Preguntalo antes de registrar.")
    for objeto in consulta:
        if pedido in (normalize_text(objeto.name), normalize_text(getattr(objeto, "slug", ""))):
            return objeto
    for objeto in consulta:
        if pedido in normalize_text(objeto.name) or normalize_text(objeto.name) in pedido:
            return objeto
    disponibles = ", ".join(o.name for o in consulta[:15])
    raise EntryError(f"No encuentro el {etiqueta} '{nombre}'. Hay: {disponibles}.")


# Lo que se puede registrar hablando. Corto y explicito: cada entrada tiene detras una
# tabla con clave unica real, y por eso volver a registrar corrige en vez de duplicar.
ENTRY_TYPES = {
    "gasto_publicitario": {
        "label": "Inversion publicitaria de un dia",
        "permission": "reports.change_dailyadspend",
        "campos": "marca, pais, plataforma, fecha y monto",
        "ejemplo": "El gasto de Meta en Bali Colombia del 3 de agosto fue 320.000",
    },
    "ventas_de_canal": {
        "label": "Ventas de un canal en un dia",
        "permission": "reports.change_dailychannelsale",
        "campos": "marca, pais, canal, fecha y monto (pedidos y unidades opcionales)",
        "ejemplo": "Ayer WhatsApp de Bali vendio 1.250.000 en 8 pedidos",
    },
}


def describe_entry_types(user):
    """Que puede registrar esta persona hablando, y con que datos."""
    from .tools import allowed_business_units

    return {
        "marcas_que_puede_actualizar": [b.name for b in allowed_business_units(user)],
        "tipos": [
            {
                "tipo": clave,
                "que_registra": spec["label"],
                "datos_que_necesito": spec["campos"],
                "ejemplo": spec["ejemplo"],
                "puede": user.has_perm(spec["permission"]),
            }
            for clave, spec in ENTRY_TYPES.items()
        ],
        "nota": (
            "Registrar el mismo dia dos veces corrige el valor, no lo suma: la tabla tiene "
            "clave unica por marca, pais, canal/plataforma y fecha."
        ),
    }


def _check_brand(user, marca):
    from .tools import allowed_business_units

    permitidas = allowed_business_units(user)
    if marca.pk not in {b.pk for b in permitidas}:
        raise EntryError(
            f"'{marca.name}' no esta entre las marcas que ves en Axis "
            f"({', '.join(b.name for b in permitidas)}), asi que no puedes registrar sus datos."
        )


def plan_entry(user, kind, **datos):
    """Valida el dato y devuelve antes/despues. No escribe nada."""
    tipo = str(kind or "").strip().lower()
    if tipo not in ENTRY_TYPES:
        raise EntryError(f"'{kind}' no se puede registrar. Se puede: {', '.join(ENTRY_TYPES)}.")

    marca = _resolve(BusinessUnit, datos.get("marca"), "marca")
    _check_brand(user, marca)
    pais = _resolve(Country, datos.get("pais"), "pais")
    dia = _day(datos.get("fecha"))
    monto = _amount(datos.get("monto"), "el monto")

    if tipo == "gasto_publicitario":
        plataforma = _resolve(AdPlatform, datos.get("plataforma"), "plataforma de pauta")
        existente = DailyAdSpend.objects.filter(
            business_unit=marca, country=pais, ad_platform=plataforma, spend_date=dia
        ).first()
        return {
            "tipo": tipo,
            "que": f"Inversion de {plataforma.name} en {marca.name} {pais.name}",
            "fecha": dia.isoformat(),
            "antes": str(existente.spend_amount) if existente else "sin dato",
            "despues": str(monto),
            "claves": {
                "marca": marca.slug, "pais": pais.code,
                "plataforma": plataforma.slug, "fecha": dia.isoformat(),
            },
            "monto": str(monto),
            "permiso": ENTRY_TYPES[tipo]["permission"],
            "aviso": (
                f"Ya habia un dato para ese dia ({existente.spend_amount}): esto lo reemplaza."
                if existente
                else ""
            ),
        }

    canal = _resolve(Channel, datos.get("canal"), "canal")
    pedidos = _count(datos.get("pedidos") or 0, "los pedidos")
    unidades = _count(datos.get("unidades") or 0, "las unidades")
    existente = DailyChannelSale.objects.filter(
        business_unit=marca, country=pais, channel=canal, sale_date=dia
    ).first()
    return {
        "tipo": tipo,
        "que": f"Ventas de {canal.name} en {marca.name} {pais.name}",
        "fecha": dia.isoformat(),
        "antes": str(existente.sales_amount) if existente else "sin dato",
        "despues": str(monto),
        "claves": {
            "marca": marca.slug, "pais": pais.code,
            "canal": canal.slug, "fecha": dia.isoformat(),
        },
        "monto": str(monto),
        "pedidos": pedidos,
        "unidades": unidades,
        "permiso": ENTRY_TYPES[tipo]["permission"],
        "aviso": (
            f"Ya habia ventas para ese dia ({existente.sales_amount}): esto las reemplaza."
            if existente
            else ""
        ),
    }


def apply_entry(user, kind, **datos):
    """Registra el dato. Solo se llama tras confirmacion humana."""
    from ..integrations.run_log import track_run
    from ..models import AiConfigChange

    plan = plan_entry(user, kind, **datos)
    if not user.has_perm(plan["permiso"]):
        raise EntryError(f"Te falta el permiso {plan['permiso']}.")

    claves = plan["claves"]
    marca = BusinessUnit.objects.get(slug=claves["marca"])
    pais = Country.objects.get(code=claves["pais"])
    dia = date.fromisoformat(claves["fecha"])
    monto = Decimal(plan["monto"])

    if plan["tipo"] == "gasto_publicitario":
        DailyAdSpend.objects.update_or_create(
            business_unit=marca, country=pais,
            ad_platform=AdPlatform.objects.get(slug=claves["plataforma"]), spend_date=dia,
            defaults={
                "spend_amount": monto,
                "source_type": DailyAdSpend.SourceType.MANUAL,
                "source_file": f"asistente ({user.get_username()})",
            },
        )
    else:
        DailyChannelSale.objects.update_or_create(
            business_unit=marca, country=pais,
            channel=Channel.objects.get(slug=claves["canal"]), sale_date=dia,
            defaults={
                "sales_amount": monto,
                "order_count": plan["pedidos"],
                "units": plan["unidades"],
                "source_type": DailyChannelSale.SourceType.MANUAL,
                "source_file": f"asistente ({user.get_username()})",
            },
        )

    with track_run(
        "IA dato manual", command=f"{plan['tipo']} (via asistente, {user.get_username()})",
        target_date=dia,
    ) as run:
        run.summary = f"{plan['que']} {plan['fecha']}: {plan['antes']} -> {plan['despues']}"

    AiConfigChange.objects.create(
        user=user, target=plan["tipo"], object_label=f"{plan['que']} {plan['fecha']}",
        field="monto", old_value=plan["antes"], new_value=plan["despues"],
    )
    return {**plan, "aplicado": True, "nota": "Este dato SI quedo registrado en Axis."}
