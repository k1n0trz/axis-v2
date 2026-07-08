import json
import os
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from reports.integrations.clients import ExchangeRateClient


class Command(BaseCommand):
    help = "Convierte montos entre divisas para el flujo diario de Helti."

    def add_arguments(self, parser):
        parser.add_argument("amount", type=str)
        parser.add_argument("--from-currency", required=True)
        parser.add_argument("--to-currency", default="COP")
        parser.add_argument("--api-url", default=os.getenv("EXCHANGE_RATE_API_URL", "https://api.exchangerate.host"))
        parser.add_argument("--api-key", default=os.getenv("EXCHANGE_RATE_API_KEY", ""))

    def handle(self, *args, **options):
        try:
            amount = Decimal(options["amount"])
        except Exception as exc:
            raise CommandError("El monto debe ser numerico.") from exc

        client = ExchangeRateClient(options["api_url"], api_key=options["api_key"])
        converted = client.convert(options["from_currency"], options["to_currency"], amount)
        self.stdout.write(
            json.dumps(
                {
                    "amount": str(amount),
                    "from_currency": options["from_currency"],
                    "to_currency": options["to_currency"],
                    "converted_amount": str(converted),
                },
                indent=2,
            )
        )
