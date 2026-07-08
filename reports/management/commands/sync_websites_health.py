import json

from django.core.management.base import BaseCommand

from reports.models import Website
from reports.services.website_monitor import scan_active_websites, scan_website, seed_websites


class Command(BaseCommand):
    help = "Crea el inventario de webs y ejecuta diagnosticos basicos de disponibilidad, SSL, seguridad y productos visibles."

    def add_arguments(self, parser):
        parser.add_argument("--seed-only", action="store_true", help="Solo crea/actualiza el inventario de webs.")
        parser.add_argument("--slug", default="", help="Escanea una sola web por slug.")
        parser.add_argument("--include-pending", action="store_true", help="Incluye webs pendientes con URL configurada.")

    def handle(self, *args, **options):
        websites = seed_websites()
        if options["seed_only"]:
            self.stdout.write(json.dumps({"seeded": len(websites)}, indent=2))
            return

        if options["slug"]:
            website = Website.objects.get(slug=options["slug"])
            checks = [scan_website(website)]
        elif options["include_pending"]:
            checks = [
                scan_website(website)
                for website in Website.objects.filter(url__gt="", monitor_enabled=True).order_by("display_order", "name")
            ]
        else:
            checks = scan_active_websites()

        payload = {
            "seeded": len(websites),
            "checked": len(checks),
            "results": [
                {
                    "website": str(check.website),
                    "slug": check.website.slug,
                    "status": check.overall_status,
                    "availability": check.availability_status,
                    "http_status": check.http_status,
                    "response_time_ms": check.response_time_ms,
                    "ssl_days_remaining": check.ssl_days_remaining,
                    "security_headers": f"{check.security_headers_score}/{check.security_headers_total}",
                    "pagespeed_status": check.pagespeed_status,
                    "performance_score": check.performance_score,
                    "accessibility_score": check.accessibility_score,
                    "best_practices_score": check.best_practices_score,
                    "seo_score": check.seo_score,
                    "error": check.error_message,
                }
                for check in checks
            ],
        }
        self.stdout.write(json.dumps(payload, indent=2, default=str))
