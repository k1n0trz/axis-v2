"""Registro de ejecuciones: quien corrio, cuando, con que resultado.

Sin esto, cuando un dato no aparece en el tablero no hay forma de distinguir tres
situaciones que se ven identicas (una celda vacia):

  - el job no corrio
  - corrio y fallo
  - corrio bien y la fuente venia vacia

Se usa como gestor de contexto para que registrar sea mas barato que no hacerlo:

    with track_run("websites_health", command="sync_websites_health") as run:
        ...
        run.summary = "4 webs revisadas, 1 en alerta"

Si el bloque lanza, la ejecucion queda como `failed` con el mensaje del error y la
excepcion se vuelve a lanzar: la bitacora no debe cambiar el comportamiento del
comando, solo dejar constancia.
"""
import logging
from contextlib import contextmanager

from django.utils import timezone

from reports.models import IntegrationRun

logger = logging.getLogger(__name__)

# El payload es para diagnosticar, no un respaldo de los datos. Se recorta para
# que un job de un mes no deje megas de JSON en la base.
MAX_PAYLOAD_CHARS = 4000


def _trim(value, limit=MAX_PAYLOAD_CHARS):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"... (recortado, {len(text)} caracteres)"


@contextmanager
def track_run(source, command="", target_date=None):
    run = IntegrationRun.objects.create(
        source=source,
        command=command,
        target_date=target_date,
        started_at=timezone.now(),
        status=IntegrationRun.Status.RUNNING,
    )
    try:
        yield run
    except Exception as exc:
        run.status = IntegrationRun.Status.FAILED
        run.error_message = _trim(f"{type(exc).__name__}: {exc}")
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        logger.exception("Integracion %s fallo", source)
        raise
    else:
        # Un comando puede declararse omitido asignando el estado el mismo.
        if run.status == IntegrationRun.Status.RUNNING:
            run.status = IntegrationRun.Status.SUCCESS
        run.summary = _trim(run.summary, 2000)
        run.error_message = _trim(run.error_message, 2000)
        run.payload = run.payload or {}
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "summary", "error_message", "payload", "finished_at", "updated_at"])


def last_run_by_source():
    """Ultima ejecucion de cada fuente. Para el tablero de estado."""
    latest = {}
    for run in IntegrationRun.objects.order_by("source", "-started_at"):
        latest.setdefault(run.source, run)
    return latest
