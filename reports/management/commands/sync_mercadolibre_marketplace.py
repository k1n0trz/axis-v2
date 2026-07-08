import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reports.services.mercadolibre_sync import configured_client, sync_inventory, sync_orders_for_day


class Command(BaseCommand):
    help = "Sincroniza inventario y ventas diarias de Mercado Libre para Marketplace."

    def add_arguments(self, parser):
        parser.add_argument("--date", default="yesterday")
        parser.add_argument("--date-start", default="")
        parser.add_argument("--date-end", default="")
        parser.add_argument("--inventory-only", action="store_true")
        parser.add_argument("--sales-only", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--status", default="active")

    def handle(self, *args, **options):
        if options["inventory_only"] and options["sales_only"]:
            raise CommandError("Usa solo una opcion: --inventory-only o --sales-only.")
        client = configured_client()
        payload = {"inventory": None, "sales": []}

        if not options["sales_only"]:
            payload["inventory"] = sync_inventory(client=client, max_items=options["limit"], status=options["status"])

        if not options["inventory_only"]:
            for target_date in self._dates(options):
                payload["sales"].append(sync_orders_for_day(target_date, client=client))

        self.stdout.write(json.dumps(payload, indent=2, default=str))

    def _dates(self, options):
        if options["date_start"] or options["date_end"]:
            if not options["date_start"] or not options["date_end"]:
                raise CommandError("Para rango debes enviar --date-start y --date-end.")
            start = date.fromisoformat(options["date_start"])
            end = date.fromisoformat(options["date_end"])
            if start > end:
                raise CommandError("--date-start no puede ser posterior a --date-end.")
            current = start
            while current <= end:
                yield current
                current += timedelta(days=1)
            return
        raw = str(options["date"] or "yesterday").strip().lower()
        if raw == "yesterday":
            yield timezone.localdate() - timedelta(days=1)
        elif raw == "today":
            yield timezone.localdate()
        else:
            yield date.fromisoformat(raw)
