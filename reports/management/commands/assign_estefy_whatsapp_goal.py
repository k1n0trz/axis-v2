from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from reports.models import BusinessUnit, Channel, SalesTarget


class Command(BaseCommand):
    help = "Create or update Estefy's monthly WhatsApp Bali sales target."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=2026)
        parser.add_argument("--month", type=int, default=4)
        parser.add_argument("--amount", default="20000000")

    def handle(self, *args, **options):
        user = User.objects.filter(username__iexact="Estefy").first()
        if not user:
            raise CommandError("No existe el usuario Estefy.")

        business_unit = BusinessUnit.objects.filter(slug="bali").first()
        channel = Channel.objects.filter(business_unit=business_unit, slug="bali-whatsapp").first()
        if not business_unit or not channel:
            raise CommandError("No existe el catalogo Bali / WhatsApp Bali.")

        year = options["year"]
        month = options["month"]
        date_start = date(year, month, 1)
        date_end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1).replace(day=1)
        date_end = date.fromordinal(date_end.toordinal() - 1)

        target, created = SalesTarget.objects.update_or_create(
            user=user,
            business_unit=business_unit,
            channel=channel,
            date_start=date_start,
            date_end=date_end,
            defaults={
                "target_amount": Decimal(options["amount"]),
                "is_active": True,
                "notes": "Meta mensual WhatsApp Bali asignada para Estefy.",
            },
        )
        action = "creada" if created else "actualizada"
        self.stdout.write(self.style.SUCCESS(f"Meta {action}: {target.target_amount} COP para {user.username}."))
