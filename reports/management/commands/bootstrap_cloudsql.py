from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run database migrations and load the Cloud SQL seed fixture."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default="data/cloudsql_seed.json",
            help="Fixture path relative to BASE_DIR.",
        )
        parser.add_argument(
            "--flush-before-load",
            action="store_true",
            help="Clear database data after migrations and before loading the fixture.",
        )

    def handle(self, *args, **options):
        fixture_path = Path(settings.BASE_DIR) / options["fixture"]
        self.stdout.write("Applying migrations...")
        call_command("migrate", interactive=False)

        if fixture_path.exists():
            if options["flush_before_load"]:
                self.stdout.write("Flushing database data before fixture load...")
                call_command("flush", interactive=False)
            self.stdout.write(f"Loading fixture {fixture_path}...")
            call_command("loaddata", str(fixture_path))
            self.stdout.write(self.style.SUCCESS("Cloud SQL seed loaded."))
        else:
            self.stdout.write(self.style.WARNING(f"Fixture not found: {fixture_path}"))
