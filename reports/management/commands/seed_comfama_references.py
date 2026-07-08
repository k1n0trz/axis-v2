import json

from django.core.management.base import BaseCommand

from reports.services.comfama_import import ensure_comfama_product_references


class Command(BaseCommand):
    help = "Carga o actualiza las referencias y tarifas canonicas de Comfama dentro de Helti."

    def handle(self, *args, **options):
        result = ensure_comfama_product_references()
        self.stdout.write(json.dumps(result, indent=2))
