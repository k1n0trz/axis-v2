"""Precalienta la cache del panel de anuncios activos de Meta.

La llamada a Meta tarda del orden de 12 segundos, asi que hacerla dentro del
request obliga al primer usuario de cada ventana de cache a esperar. Este
comando la hace en segundo plano, con un timeout holgado, para que la pagina
siempre encuentre el panel listo en cache.

Se precalientan las combinaciones que la aplicacion pide por defecto:
el mes en curso, por pais, y el alcance Comfama para Colombia.
"""
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.integrations.run_log import track_run
from reports.services.sales_dashboard import build_uva_meta_ads_preview

# (codigo de pais, alcance) -> lo que piden /uva/ y /uva/comfama/
DEFAULT_TARGETS = (
    ("CO", "exclude"),
    ("MX", "exclude"),
    ("EC", "exclude"),
    ("CO", "only"),
)


class Command(BaseCommand):
    help = "Precalienta en cache el panel de anuncios activos de Meta Ads."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=90,
            help="Segundos de espera por llamada a Meta. Holgado a proposito: nadie esta esperando.",
        )
        parser.add_argument(
            "--date-start",
            help="Inicio del rango (YYYY-MM-DD). Por defecto, el primer dia del mes en curso.",
        )
        parser.add_argument(
            "--date-end",
            help="Fin del rango (YYYY-MM-DD). Por defecto, hoy.",
        )
        parser.add_argument(
            "--country",
            action="append",
            dest="countries",
            help="Limita a estos paises (repetible). Por defecto CO, MX y EC.",
        )

    def handle(self, *args, **options):
        with track_run("meta_ads_preview_warmup", command="warm_meta_ads_preview") as run:
            self._warm(options, run)

    def _warm(self, options, run):
        today = timezone.localdate()
        date_start = self._parse_date(options.get("date_start")) or today.replace(day=1)
        date_end = self._parse_date(options.get("date_end")) or today
        only_countries = {value.upper() for value in (options.get("countries") or [])}

        targets = [
            (country, scope)
            for country, scope in DEFAULT_TARGETS
            if not only_countries or country in only_countries
        ]

        warmed = 0
        skipped = 0
        failed = 0
        for country, scope in targets:
            if not getattr(settings, f"META_{country}_ACCOUNT_ID", ""):
                self.stdout.write(f"  {country}/{scope}: sin cuenta Meta configurada, se omite.")
                skipped += 1
                continue

            filters = {
                "country": country,
                "date_start": date_start.isoformat(),
                "date_end": date_end.isoformat(),
            }
            preview = build_uva_meta_ads_preview(
                filters,
                comfama_scope=scope,
                force_refresh=True,
                timeout=options["timeout"],
            )
            ad_count = len(preview.get("ads") or [])
            if ad_count:
                self.stdout.write(self.style.SUCCESS(f"  {country}/{scope}: {ad_count} anuncios en cache."))
                warmed += 1
            elif preview.get("message"):
                self.stdout.write(self.style.WARNING(f"  {country}/{scope}: {preview['message']}"))
                failed += 1
            else:
                self.stdout.write(f"  {country}/{scope}: sin anuncios activos.")
                skipped += 1

        resumen = f"Precalentamiento Meta del {date_start} al {date_end}. Listos: {warmed}. Omitidos: {skipped}. Con problema: {failed}."
        self.stdout.write(self.style.SUCCESS(resumen) if not failed else self.style.WARNING(resumen))
        run.summary = resumen
        run.target_date = date_end
        run.payload = {"warmed": warmed, "skipped": skipped, "failed": failed,
                       "date_start": date_start.isoformat(), "date_end": date_end.isoformat()}
        # Un precalentamiento que no dejo nada listo no es un exito silencioso: la
        # pagina va a mostrar el panel vacio y alguien tiene que enterarse.
        if failed and not warmed:
            run.status = run.Status.FAILED
            run.error_message = resumen
        elif not warmed:
            run.status = run.Status.SKIPPED

    def _parse_date(self, raw):
        if not raw:
            return None
        return date.fromisoformat(str(raw))
