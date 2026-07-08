from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from reports.models import ComfamaAdMetric, ComfamaSale, DailyAdSpend


class Command(BaseCommand):
    help = "Elimina todos los datos Comfama del ano 2024."

    def handle(self, *args, **options):
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        with transaction.atomic():
            sales_deleted, _ = ComfamaSale.objects.filter(sale_date__range=(start, end)).delete()
            metrics_deleted, _ = ComfamaAdMetric.objects.filter(metric_date__range=(start, end)).delete()
            spend_deleted, _ = DailyAdSpend.objects.filter(
                business_unit__slug="comfama-uva",
                spend_date__range=(start, end),
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Datos Comfama 2024 eliminados. "
                f"Ventas: {sales_deleted}. Metricas: {metrics_deleted}. Pauta diaria: {spend_deleted}."
            )
        )
