"""Estado de Axis en una sola salida, para inspeccionar produccion sin `shell -c`.

Existe porque `gcloud run jobs execute --args` separa por comas y rompe cualquier
codigo Python que las use, asi que consultar la base de produccion por ahi es
inviable. Este comando no recibe argumentos y su salida es JSON.
"""
import json

from django.core.management.base import BaseCommand
from django.db.models import Max

from reports import models as m

DATED = (
    ("DailyChannelSale", "sale_date"),
    ("DailyProductCategorySale", "sale_date"),
    ("DailyAdSpend", "spend_date"),
    ("DailyProductCategoryMetric", "metric_date"),
    ("BaliDailyMetric", "metric_date"),
    ("ComfamaSale", "sale_date"),
    ("WebsiteHealthCheck", "checked_at"),
    ("IntegrationRun", "started_at"),
)
# Modulo apagado desde antes. Se cuenta para saber si se puede retirar sin perder nada.
TASKS_AND_GOALS = (
    "UserTask", "UserTaskAttachment", "UserTaskLink", "SalesTarget",
    "OperationalGoalTask", "OperationalGoalTaskAttachment",
    "InsightAchievement", "AgendaTask", "WeeklyTask", "Task",
)


class Command(BaseCommand):
    help = "Imprime en JSON el estado de los datos de Axis: filas, ultima fecha y bitacora."

    def handle(self, *args, **options):
        payload = {"data": {}, "tasks_and_goals": {}, "last_runs": {}}

        for name, field in DATED:
            model = getattr(m, name, None)
            if model is None:
                continue
            queryset = model.objects.all()
            payload["data"][name] = {
                "rows": queryset.count(),
                "latest": str(queryset.aggregate(v=Max(field))["v"] or ""),
            }

        for name in TASKS_AND_GOALS:
            model = getattr(m, name, None)
            payload["tasks_and_goals"][name] = model.objects.count() if model else None
        payload["tasks_and_goals_total"] = sum(v for v in payload["tasks_and_goals"].values() if v)

        for run in m.IntegrationRun.objects.order_by("source", "-started_at"):
            payload["last_runs"].setdefault(
                run.source,
                {"status": run.status, "date": str(run.target_date or ""), "summary": run.summary[:90]},
            )

        payload["business_units"] = list(
            m.BusinessUnit.objects.filter(is_active=True).order_by("display_order").values_list("slug", flat=True)
        )
        self.stdout.write(json.dumps(payload, indent=2, default=str))
