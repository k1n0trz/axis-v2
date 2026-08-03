"""Destila memorias y resume conversaciones. Lo lanza el job diario.

Corre fuera del chat a proposito: destilar cuesta una llamada por conversacion, y
cobrarsela al usuario en cada mensaje para adivinar si dijo algo memorable seria caro
y lento. Aqui pasa una vez al dia, sobre lo que cambio.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from reports.ai.context import is_ai_enabled
from reports.ai.distill import distill_conversation, summarize_conversation
from reports.integrations.run_log import track_run
from reports.models import AiConversation, IntegrationRun

# Techo de conversaciones por corrida. Sin techo, un dia con mucho uso dispara una
# llamada por conversacion sin que nadie haya decidido ese gasto.
MAX_PER_RUN = 40


class Command(BaseCommand):
    help = "Extrae memorias y resume conversaciones de la IA interna."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=2, help="Ventana de conversaciones a revisar.")
        parser.add_argument("--limit", type=int, default=MAX_PER_RUN)
        parser.add_argument("--user", default="", help="Solo este usuario.")

    def handle(self, *args, **options):
        with track_run("IA memorias", command="distill_ai_memories") as run:
            if not is_ai_enabled():
                run.status = IntegrationRun.Status.SKIPPED
                run.summary = "El asistente no esta configurado en este entorno."
                self.stdout.write("Sin clave de IA: no hay nada que destilar.")
                return

            desde = timezone.now() - timedelta(days=max(1, options["days"]))
            conversaciones = AiConversation.objects.filter(
                updated_at__gte=desde, is_active=True
            ).filter(Q(distilled_at__isnull=True) | Q(distilled_at__lt=desde))
            if options["user"]:
                conversaciones = conversaciones.filter(user__username=options["user"])
            conversaciones = list(conversaciones.order_by("-updated_at")[: options["limit"]])

            memorias = 0
            resumidas = 0
            for conversacion in conversaciones:
                # Resumir antes de destilar: si se resume, la distilacion ya no ve los
                # turnos viejos crudos y sale mas barata.
                if summarize_conversation(conversacion):
                    resumidas += 1
                memorias += len(distill_conversation(conversacion))

            resumen = (
                f"{len(conversaciones)} conversaciones revisadas, "
                f"{memorias} memorias nuevas, {resumidas} resumidas"
            )
            run.summary = resumen
            self.stdout.write(self.style.SUCCESS(resumen))
