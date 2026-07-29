"""Memoizacion de lecturas repetidas dentro de una misma peticion.

Los constructores de tableros piden las mismas filas varias veces por render:
`build_sales_snapshot` consulta `daily_channel_sales` dos veces (una en
`_combined_direct_sales` y otra en `_daily_order_counts_by_channel`), y lo mismo
pasa con las ventas por categoria. Son lecturas puras con argumentos identicos,
asi que basta con recordar el resultado durante la peticion.

El alcance es deliberadamente la peticion, no un TTL: asi nunca se sirven datos
de una peticion anterior. Fuera de una peticion (comandos de gestion, jobs) las
funciones pasan de largo sin memoizar, para que un proceso que escribe y luego
lee siga viendo lo que acaba de guardar.
"""
import contextvars
import functools
import json

_store = contextvars.ContextVar("axis_query_memo", default=None)


class request_scope:
    """Abre un ambito de memoizacion. Sin esto, las funciones no cachean nada."""

    def __enter__(self):
        self._token = _store.set({})
        return self

    def __exit__(self, *exc_info):
        _store.reset(self._token)
        return False


def _key_part(value):
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return repr(value)


def memoize_per_request(func):
    """Recuerda el resultado de `func` para argumentos identicos en la peticion.

    Devuelve una copia superficial cuando el resultado es una lista, para que
    quien la reciba pueda ordenarla o filtrarla sin corromper lo memoizado.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        store = _store.get()
        if store is None:
            return func(*args, **kwargs)

        key = (func.__qualname__, tuple(_key_part(a) for a in args), tuple(sorted((k, _key_part(v)) for k, v in kwargs.items())))
        if key not in store:
            store[key] = func(*args, **kwargs)
        cached = store[key]
        return list(cached) if isinstance(cached, list) else cached

    wrapper.uncached = func
    return wrapper


class QueryMemoMiddleware:
    """Abre un ambito de memoizacion por peticion."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with request_scope():
            return self.get_response(request)
