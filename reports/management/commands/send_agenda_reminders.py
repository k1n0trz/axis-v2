from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.models import AgendaTask


class Command(BaseCommand):
    help = "Envia recordatorios por correo para tareas de agenda pendientes."

    def handle(self, *args, **options):
        now = timezone.now()
        queryset = AgendaTask.objects.select_related("assigned_to").filter(
            reminder_enabled=True,
            reminder_at__isnull=False,
            reminder_at__lte=now,
            reminder_sent_at__isnull=True,
            status__in=[AgendaTask.Status.PENDING, AgendaTask.Status.IN_PROGRESS],
            assigned_to__email__gt="",
        )

        sent_count = 0
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@axis.local")
        for task in queryset:
            send_mail(
                subject=f"Recordatorio de tarea: {task.title}",
                message=(
                    f"Tienes una tarea pendiente en Agenda.\n\n"
                    f"Tarea: {task.title}\n"
                    f"Fecha de finalizacion: {timezone.localtime(task.due_at).strftime('%Y-%m-%d %H:%M')}\n"
                    f"Estado: {task.get_status_display()}\n\n"
                    f"Detalle:\n{task.description or 'Sin descripcion'}"
                ),
                from_email=from_email,
                recipient_list=[task.assigned_to.email],
                fail_silently=False,
            )
            task.reminder_sent_at = now
            task.save(update_fields=["reminder_sent_at", "updated_at"])
            sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"Recordatorios enviados: {sent_count}"))
