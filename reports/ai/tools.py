"""Las consultas que la IA puede hacer contra Axis.

Existen por una razon concreta y medida. Sin herramientas, a la pregunta "un ROAS de
1500 en DistriSex es bueno" el modelo contesto hablando de **euros** en una empresa
colombiana y leyendo 1500 como 1500%. Con seguridad total. Un asistente que inventa
cifras sobre un tablero de datos es peor que no tener asistente.

Tres reglas que no se negocian:

**El modelo no escribe consultas.** Elige una funcion de esta lista y pasa parametros.
No hay SQL, ni nombres de campo, ni `eval`. Lo que no esta aqui no se puede consultar.

**Cada consulta se filtra por lo que el usuario puede ver.** Si su `UserProfile` solo
tiene Bali, preguntar por Uva devuelve vacio con una nota. La IA no es una puerta
lateral a datos que la persona no ve en el tablero.

**Los numeros se calculan aca, no alla.** ROAS, ticket y variaciones salen de la base y
llegan ya resueltos. El modelo solo los redacta. Y cuando un cociente no significa nada
—inversion casi cero, como en DistriSex— se devuelve `null` con el motivo, en vez de un
1500 que invita a leerlo como rendimiento de pauta.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from ..models import (
    AdPlatform,
    BusinessUnit,
    Channel,
    Country,
    DailyAdSpend,
    DailyChannelSale,
    DailyProductCategorySale,
    Website,
)
from ..services.common import ZERO, normalize_text, safe_ratio

# Ventana maxima por consulta. Sin techo, "compara todo el historico" barre la tabla
# entera y devuelve un payload que no cabe en el contexto.
MAX_RANGE_DAYS = 400
MAX_ROWS = 40
# Debajo de esto la inversion no sostiene un cociente: el ROAS sale null con el motivo.
MIN_SPEND_FOR_ROAS = Decimal("10000")


class ToolError(Exception):
    """Parametro invalido. Se le devuelve al modelo para que corrija, no al usuario."""


def allowed_business_units(user):
    """Las marcas que esta persona ve en el tablero. La IA no ve mas que eso."""
    profile = getattr(user, "profile", None)
    asignadas = list(profile.business_units.all()) if profile else []
    if asignadas:
        return asignadas
    return list(BusinessUnit.objects.filter(is_active=True).order_by("display_order"))


def _parse_day(raw, campo):
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw).strip())
    except (TypeError, ValueError):
        raise ToolError(f"{campo} debe venir como AAAA-MM-DD, llego '{raw}'.")


def _range(date_start, date_end):
    inicio = _parse_day(date_start, "date_start")
    fin = _parse_day(date_end, "date_end")
    if fin < inicio:
        inicio, fin = fin, inicio
    if (fin - inicio).days > MAX_RANGE_DAYS:
        raise ToolError(
            f"El rango no puede pasar de {MAX_RANGE_DAYS} dias. Pide un periodo mas corto."
        )
    return inicio, fin


def _money(value):
    """Formato colombiano, resuelto aca: el modelo cambiaba el separador y la moneda."""
    entero = int(Decimal(value or 0).quantize(Decimal("1")))
    return f"{entero:,}".replace(",", ".") + " COP"


def match_business_units(permitidas, consulta):
    """Las marcas permitidas que coinciden con lo que pidio el modelo.

    La comparacion era exacta contra nombre o slug, y eso dejaba fuera dos formas de
    pedir lo mismo que la gente usa todos los dias: el plural ("Marketplaces") y el
    apocope ("Distri"). Primero se busca exacto --asi "Uva" no arrastra "Comfama Uva"--
    y solo si no hay nada se acepta que uno contenga al otro.
    """
    pedido = normalize_text(consulta)
    if not pedido:
        return list(permitidas)

    exactas = [b for b in permitidas if pedido in (normalize_text(b.name), normalize_text(b.slug))]
    if exactas:
        return exactas
    return [
        b
        for b in permitidas
        if pedido in normalize_text(b.name) or normalize_text(b.name) in pedido
    ]


def _scope(queryset, user, business_unit="", country="", campo_unidad="business_unit"):
    """Aplica el filtro de permisos y los filtros que pidio el modelo."""
    permitidas = allowed_business_units(user)
    queryset = queryset.filter(**{f"{campo_unidad}__in": permitidas})
    nota = ""

    if business_unit:
        elegidas = match_business_units(permitidas, business_unit)
        if not elegidas:
            # `is_active=True` importa: sin eso, un duplicado desactivado que quedo en la
            # base hacia decir "existe pero no tienes acceso", que es doblemente falso.
            otra = BusinessUnit.objects.filter(name__iexact=business_unit, is_active=True).first()
            disponibles = ", ".join(b.name for b in permitidas)
            nota = (
                f"'{business_unit}' existe pero esta persona no tiene acceso. "
                f"Solo ve: {disponibles}."
                if otra
                else f"No hay ninguna marca activa llamada '{business_unit}'. Hay: {disponibles}."
            )
            return queryset.none(), nota
        queryset = queryset.filter(**{f"{campo_unidad}__in": elegidas})

    if country:
        queryset = queryset.filter(country__code__iexact=country) | queryset.filter(
            country__name__iexact=country
        )
    return queryset, nota


def list_dimensions(user, **_):
    """Que marcas, paises, canales y plataformas puede consultar esta persona."""
    permitidas = allowed_business_units(user)
    return {
        "hoy": timezone.localdate().isoformat(),
        "business_units": [b.name for b in permitidas],
        "countries": [
            {"name": c.name, "code": c.code}
            for c in Country.objects.filter(is_active=True).order_by("display_order")
        ],
        "channels": [c.name for c in Channel.objects.filter(is_active=True).order_by("name")],
        "ad_platforms": [p.name for p in AdPlatform.objects.filter(is_active=True).order_by("name")],
        "nota": "La moneda de todos los importes es COP.",
    }


def get_performance(user, date_start, date_end, business_unit="", country="", **_):
    """Ventas, inversion, ROAS y ticket del periodo. La que responde casi todo."""
    inicio, fin = _range(date_start, date_end)

    ventas_qs, nota = _scope(
        DailyChannelSale.objects.filter(sale_date__range=(inicio, fin)), user, business_unit, country
    )
    ventas = ventas_qs.aggregate(
        total=Sum("sales_amount"), pedidos=Sum("order_count"), unidades=Sum("units")
    )
    gasto_qs, _nota_gasto = _scope(
        DailyAdSpend.objects.filter(spend_date__range=(inicio, fin)), user, business_unit, country
    )
    gasto = gasto_qs.aggregate(total=Sum("spend_amount"))

    total_ventas = ventas["total"] or ZERO
    total_gasto = gasto["total"] or ZERO
    pedidos = ventas["pedidos"] or 0

    if total_gasto < MIN_SPEND_FOR_ROAS:
        roas = None
        nota_roas = (
            f"La inversion del periodo ({_money(total_gasto)}) es demasiado baja para que "
            "el ROAS signifique algo. No lo presentes como rendimiento de pauta."
        )
    else:
        roas = float(round(safe_ratio(total_ventas, total_gasto), 2))
        nota_roas = ""

    return {
        "periodo": f"{inicio.isoformat()} a {fin.isoformat()}",
        "ventas_cop": _money(total_ventas),
        "ventas": float(total_ventas),
        "inversion_cop": _money(total_gasto),
        "inversion": float(total_gasto),
        "pedidos": pedidos,
        "unidades": ventas["unidades"] or 0,
        "ticket_promedio_cop": _money(safe_ratio(total_ventas, pedidos)) if pedidos else None,
        "roas": roas,
        "filas_de_venta": ventas_qs.count(),
        "nota": " ".join(p for p in (nota, nota_roas) if p),
    }


def get_sales(user, date_start, date_end, business_unit="", country="", group_by="total", **_):
    """Ventas del periodo, con desglose opcional."""
    inicio, fin = _range(date_start, date_end)
    queryset, nota = _scope(
        DailyChannelSale.objects.filter(sale_date__range=(inicio, fin)), user, business_unit, country
    )

    agrupaciones = {
        "total": None,
        "business_unit": "business_unit__name",
        "country": "country__name",
        "channel": "channel__name",
        "date": "sale_date",
    }
    if group_by not in agrupaciones:
        raise ToolError(f"group_by debe ser uno de: {', '.join(agrupaciones)}.")

    total = queryset.aggregate(total=Sum("sales_amount"), pedidos=Sum("order_count"))
    resultado = {
        "periodo": f"{inicio.isoformat()} a {fin.isoformat()}",
        "total_cop": _money(total["total"] or ZERO),
        "pedidos": total["pedidos"] or 0,
        "nota": nota,
    }

    campo = agrupaciones[group_by]
    if campo:
        filas = (
            queryset.values(campo)
            .annotate(ventas=Sum("sales_amount"), pedidos=Sum("order_count"))
            .order_by("-ventas")[:MAX_ROWS]
        )
        resultado["desglose"] = [
            {
                "clave": str(f[campo]),
                "ventas_cop": _money(f["ventas"]),
                "ventas": float(f["ventas"] or 0),
                "pedidos": f["pedidos"] or 0,
            }
            for f in filas
        ]
    return resultado


def get_ad_spend(user, date_start, date_end, business_unit="", country="", group_by="platform", **_):
    """Inversion publicitaria del periodo."""
    inicio, fin = _range(date_start, date_end)
    queryset, nota = _scope(
        DailyAdSpend.objects.filter(spend_date__range=(inicio, fin)), user, business_unit, country
    )

    agrupaciones = {
        "total": None,
        "platform": "ad_platform__name",
        "business_unit": "business_unit__name",
        "country": "country__name",
        "date": "spend_date",
    }
    if group_by not in agrupaciones:
        raise ToolError(f"group_by debe ser uno de: {', '.join(agrupaciones)}.")

    total = queryset.aggregate(total=Sum("spend_amount"))
    resultado = {
        "periodo": f"{inicio.isoformat()} a {fin.isoformat()}",
        "total_cop": _money(total["total"] or ZERO),
        "nota": nota,
    }
    campo = agrupaciones[group_by]
    if campo:
        filas = queryset.values(campo).annotate(gasto=Sum("spend_amount")).order_by("-gasto")[:MAX_ROWS]
        resultado["desglose"] = [
            {"clave": str(f[campo]), "inversion_cop": _money(f["gasto"]), "inversion": float(f["gasto"] or 0)}
            for f in filas
        ]
    return resultado


def get_category_sales(user, date_start, date_end, business_unit="", country="", limit=10, **_):
    """Que categorias de producto vendieron mas en el periodo."""
    inicio, fin = _range(date_start, date_end)
    queryset, nota = _scope(
        DailyProductCategorySale.objects.filter(sale_date__range=(inicio, fin)),
        user,
        business_unit,
        country,
    )
    tope = max(1, min(int(limit or 10), MAX_ROWS))
    filas = (
        queryset.values("category__name")
        .annotate(ventas=Sum("sales_amount"), unidades=Sum("quantity"))
        .order_by("-ventas")[:tope]
    )
    return {
        "periodo": f"{inicio.isoformat()} a {fin.isoformat()}",
        "categorias": [
            {
                "categoria": f["category__name"],
                "ventas_cop": _money(f["ventas"]),
                "ventas": float(f["ventas"] or 0),
                "unidades": f["unidades"] or 0,
            }
            for f in filas
        ],
        "nota": nota,
    }


def get_data_freshness(user, **_):
    """Hasta que dia hay datos y como le fue a cada fuente. Para "esta al dia?"."""
    from ..integrations.run_log import last_run_by_source

    permitidas = allowed_business_units(user)
    ultima_venta = (
        DailyChannelSale.objects.filter(business_unit__in=permitidas)
        .order_by("-sale_date")
        .values_list("sale_date", flat=True)
        .first()
    )
    ultima_inversion = (
        DailyAdSpend.objects.filter(business_unit__in=permitidas)
        .order_by("-spend_date")
        .values_list("spend_date", flat=True)
        .first()
    )
    fuentes = []
    for nombre, corrida in sorted(last_run_by_source().items()):
        fuentes.append({
            "fuente": nombre,
            "estado": corrida.get_status_display(),
            "cuando": corrida.started_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M"),
            "resumen": (corrida.summary or corrida.error_message or "")[:200],
        })
    return {
        "hoy": timezone.localdate().isoformat(),
        "ultima_venta_registrada": ultima_venta.isoformat() if ultima_venta else None,
        "ultima_inversion_registrada": ultima_inversion.isoformat() if ultima_inversion else None,
        "fuentes": fuentes[:MAX_ROWS],
    }


def list_my_files(user, **_):
    """Los archivos que esta persona le paso a la IA, de esta sesion y de las anteriores.

    Solo el inventario: leer el contenido de un Excel llega en la Etapa G, con los
    parsers que ya existen. Aca la IA solo sabe que archivos tiene a mano.
    """
    from .attachments import list_attachments

    return {
        "archivos": [
            {
                "id": a.pk,
                "nombre": a.original_name,
                "tipo": a.content_type,
                "kb": round(a.size_bytes / 1024),
                "subido": a.created_at.strftime("%Y-%m-%d %H:%M"),
                "descripcion": a.description,
            }
            for a in list_attachments(user)[:MAX_ROWS]
        ],
        "nota": "Todavia no puedes leer el contenido de estos archivos, solo saber que existen.",
    }


def describe_file(user, attachment_id, **_):
    """Que hay dentro de un Excel que subio esta persona, sin escribir nada."""
    from .spreadsheets import attachment_for, describe_attachment

    attachment = attachment_for(user, attachment_id)
    if not attachment:
        return {"error": "No encuentro ese archivo entre los tuyos. Usa list_my_files."}
    return describe_attachment(attachment)


def preview_file_import(user, attachment_id, sheet="", **_):
    """Simula la carga: corre el importador real y deshace la transaccion.

    No escribe. Lo que devuelve es el diff medido, no una prediccion: es la unica forma
    de que la vista previa no se desincronice del importador.
    """
    from .spreadsheets import AttachmentGone, ImportNotPossible, attachment_for, preview_import

    attachment = attachment_for(user, attachment_id)
    if not attachment:
        return {"error": "No encuentro ese archivo entre los tuyos. Usa list_my_files."}
    try:
        return preview_import(attachment, sheet_name=sheet)
    except (ImportNotPossible, AttachmentGone) as exc:
        return {"error": str(exc)}


def get_config(user, **_):
    """Que se puede cambiar sin desplegar codigo, y como esta hoy."""
    from .config_changes import describe_config

    return describe_config(user)


def preview_config_change(user, target, name, field, value, **_):
    """Valida un cambio de configuracion y lo muestra. NO lo aplica.

    Lo aplica una persona con el boton, igual que la carga de archivos. El boton lo
    dibuja el widget con **esta** salida, no con lo que el modelo escriba en su texto:
    asi lo que se confirma es exactamente lo que se valido.
    """
    from .config_changes import ConfigError, plan_change

    try:
        plan = plan_change(user, target, name, field, value)
    except ConfigError as exc:
        return {"error": str(exc)}
    return {**plan, "aplicado": False, "nota": "Todavia no se aplico: falta que la persona confirme."}


def get_websites_health(user, **_):
    """Estado de las webs monitoreadas."""
    permitidas = allowed_business_units(user)
    sitios = (
        Website.objects.filter(monitor_enabled=True)
        .filter(business_unit__in=permitidas)
        .select_related("business_unit")
        .order_by("display_order", "name")[:MAX_ROWS]
    )
    filas = []
    for sitio in sitios:
        ultimo = getattr(sitio, "latest_check", None) or sitio.checks.order_by("-checked_at").first()
        filas.append({
            "web": sitio.name,
            "url": sitio.url,
            "marca": sitio.business_unit.name if sitio.business_unit else "",
            "plataforma": sitio.get_platform_display(),
            "estado_http": getattr(ultimo, "status_code", None),
            "revisada": ultimo.checked_at.strftime("%Y-%m-%d %H:%M") if ultimo else None,
            "pagespeed_movil": getattr(ultimo, "pagespeed_mobile_score", None),
            "pagespeed_estado": getattr(ultimo, "pagespeed_status", ""),
        })
    return {"webs": filas, "nota": "pagespeed_estado 'stale' significa que es la ultima medicion buena, no la de hoy."}


# El registro. Lo que no este aca, la IA no lo puede consultar.
TOOLS = {
    "list_dimensions": list_dimensions,
    "get_performance": get_performance,
    "get_sales": get_sales,
    "get_ad_spend": get_ad_spend,
    "get_category_sales": get_category_sales,
    "get_data_freshness": get_data_freshness,
    "get_websites_health": get_websites_health,
    "list_my_files": list_my_files,
    "describe_file": describe_file,
    "get_config": get_config,
    "preview_config_change": preview_config_change,
    "preview_file_import": preview_file_import,
}

_RANGO = {
    "date_start": {"type": "string", "description": "Dia inicial, AAAA-MM-DD."},
    "date_end": {"type": "string", "description": "Dia final, AAAA-MM-DD."},
}
_FILTROS = {
    "business_unit": {"type": "string", "description": "Marca: Uva, Bali, DistriSex, Marketplace. Vacio = todas las que ve."},
    "country": {"type": "string", "description": "Pais por nombre o codigo (CO, EC, MX). Vacio = todos."},
}


def _spec(name, description, properties, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required)},
        },
    }


TOOL_SPECS = [
    _spec(
        "list_dimensions",
        "Marcas, paises, canales y plataformas que esta persona puede consultar, y la fecha de hoy. "
        "Usala si no sabes como se llama exactamente algo.",
        {},
    ),
    _spec(
        "get_performance",
        "Ventas, inversion, ROAS, pedidos y ticket promedio de un periodo. Es la primera opcion "
        "para casi cualquier pregunta de resultados.",
        {**_RANGO, **_FILTROS},
        ("date_start", "date_end"),
    ),
    _spec(
        "get_sales",
        "Ventas de un periodo, con desglose opcional por marca, pais, canal o dia.",
        {
            **_RANGO,
            **_FILTROS,
            "group_by": {
                "type": "string",
                "enum": ["total", "business_unit", "country", "channel", "date"],
                "description": "Como desglosar. 'total' devuelve solo el total.",
            },
        },
        ("date_start", "date_end"),
    ),
    _spec(
        "get_ad_spend",
        "Inversion publicitaria de un periodo, con desglose por plataforma, marca, pais o dia.",
        {
            **_RANGO,
            **_FILTROS,
            "group_by": {
                "type": "string",
                "enum": ["total", "platform", "business_unit", "country", "date"],
            },
        },
        ("date_start", "date_end"),
    ),
    _spec(
        "get_category_sales",
        "Categorias de producto que mas vendieron en un periodo.",
        {**_RANGO, **_FILTROS, "limit": {"type": "integer", "description": "Cuantas devolver, maximo 40."}},
        ("date_start", "date_end"),
    ),
    _spec(
        "get_data_freshness",
        "Hasta que dia hay datos cargados y como le fue a cada fuente en su ultima corrida. "
        "Usala si preguntan si el tablero esta al dia o si un numero se ve raro.",
        {},
    ),
    _spec(
        "get_websites_health",
        "Estado de las webs monitoreadas: HTTP, cuando se reviso y puntaje de PageSpeed.",
        {},
    ),
    _spec(
        "get_config",
        "Marcas, paises, canales y umbrales del semaforo de ROAS, con los campos que se "
        "pueden cambiar sin desplegar codigo. Solo se **editan** los que ya existen: "
        "crear una marca o un pais nuevo, y borrar cualquiera, no se puede por aqui.",
        {},
    ),
    _spec(
        "preview_config_change",
        "Valida un cambio de configuracion y muestra el antes/despues. NO lo aplica: lo "
        "confirma la persona con un boton. Usala cuando pidan cambiar una marca, un pais, "
        "un canal o los umbrales del semaforo.",
        {
            "target": {"type": "string", "enum": ["marca", "pais", "canal", "semaforo_roas"]},
            "name": {"type": "string", "description": "Cual, por nombre. Para el semaforo puede ir vacio."},
            "field": {"type": "string", "description": "Campo a cambiar. get_config lista los validos."},
            "value": {"type": "string", "description": "Valor nuevo."},
        },
        ("target", "name", "field", "value"),
    ),
    _spec(
        "list_my_files",
        "Archivos que esta persona te ha pasado, de esta sesion y de las anteriores.",
        {},
    ),
    _spec(
        "describe_file",
        "Mira dentro de un Excel subido: hojas, fila de cabecera, columnas, una muestra "
        "de filas y si Axis reconoce su forma. No escribe nada.",
        {"attachment_id": {"type": "integer", "description": "Id que devuelve list_my_files."}},
        ("attachment_id",),
    ),
    _spec(
        "preview_file_import",
        "Simula cargar el archivo: corre el importador real y deshace la transaccion, y "
        "devuelve cuantas filas y cuanto monto cambiarian. NO escribe nada. Usala siempre "
        "antes de proponer una carga, y muestrale el resultado a la persona.",
        {
            "attachment_id": {"type": "integer"},
            "sheet": {"type": "string", "description": "Hoja, si el archivo tiene varias importables."},
        },
        ("attachment_id",),
    ),
]


def run_tool(user, name, arguments):
    """Ejecuta una consulta del registro. Nunca lanza hacia el usuario."""
    funcion = TOOLS.get(name)
    if not funcion:
        return {"error": f"No existe la consulta '{name}'."}
    try:
        return funcion(user, **(arguments or {}))
    except ToolError as exc:
        # El modelo puede corregir y reintentar: esto es para el, no para el usuario.
        return {"error": str(exc)}
    except TypeError as exc:
        return {"error": f"Parametros invalidos para {name}: {exc}"}
