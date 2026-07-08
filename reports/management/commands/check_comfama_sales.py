from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min

from reports.models import ComfamaSale


class Command(BaseCommand):
    help = "Muestra conteos y fechas recientes de ventas Comfama."

    def handle(self, *args, **options):
        summary = ComfamaSale.objects.aggregate(total=Count("id"), min_date=Min("sale_date"), max_date=Max("sale_date"))
        recent_dates = ComfamaSale.objects.values("sale_date").annotate(total=Count("id")).order_by("-sale_date")[:5]
        self.stdout.write(f"Resumen Comfama: {summary}")
        self.stdout.write(f"Fechas recientes Comfama: {list(recent_dates)}")
