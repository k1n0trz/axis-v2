from datetime import date, timedelta

from django.core.management.base import BaseCommand

from reports.models import BaliCommunityWebcamMetric
from reports.services.sales_dashboard import ensure_bali_catalogs


class Command(BaseCommand):
    help = "Carga la semilla inicial de suscritos de Comunidad Webcam Bali."

    def add_arguments(self, parser):
        parser.add_argument("--start-date", default="2026-04-01")
        parser.add_argument("--end-date", default="2026-05-06")
        parser.add_argument("--total", type=int, default=233)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        start_date = date.fromisoformat(options["start_date"])
        end_date = date.fromisoformat(options["end_date"])
        total = options["total"]
        dry_run = options["dry_run"]
        if end_date < start_date:
            raise ValueError("La fecha final no puede ser menor que la inicial.")

        days = (end_date - start_date).days + 1
        pattern = [4, 7, 5, 8, 6, 9, 3, 7, 6, 5, 8, 4, 10, 6, 7, 5, 9, 6, 4, 8, 7, 5, 6, 11]
        increments = [pattern[index % len(pattern)] for index in range(days)]
        difference = total - sum(increments)
        index = days - 1
        while difference:
            step = 1 if difference > 0 else -1
            if increments[index] + step > 0:
                increments[index] += step
                difference -= step
            index = (index - 1) % days

        catalogs = ensure_bali_catalogs()
        business_unit = catalogs["business_unit"]
        country = catalogs["country"]
        created = 0
        updated = 0
        cumulative = 0
        for offset, new_subscribers in enumerate(increments):
            metric_date = start_date + timedelta(days=offset)
            cumulative += new_subscribers
            if dry_run:
                self.stdout.write(f"{metric_date}: +{new_subscribers} -> {cumulative}")
                continue
            _, was_created = BaliCommunityWebcamMetric.objects.update_or_create(
                business_unit=business_unit,
                country=country,
                metric_date=metric_date,
                defaults={
                    "new_subscribers": new_subscribers,
                    "subscribers": cumulative,
                    "notes": "Semilla inicial autorizada para reconstruir el historico de Comunidad Webcam.",
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Comunidad Webcam Bali cargada: {created} creados, {updated} actualizados, total final {cumulative} suscritos."
            )
        )
