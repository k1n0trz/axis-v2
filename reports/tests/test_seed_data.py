from django.core.management import call_command
from django.test import TestCase

from reports.models import BusinessUnit, Channel


class SeedDataCommandTests(TestCase):
    def test_seed_data_updates_existing_channel_matching_unique_constraint(self):
        uva = BusinessUnit.objects.create(name="Uva", slug="uva")
        Channel.objects.create(name="WhatsApp Colombia", slug="whatsapp", business_unit=uva)

        call_command("seed_data")
        call_command("seed_data")

        channel = Channel.objects.get(name="WhatsApp Colombia", business_unit__slug="uva")
        self.assertEqual(channel.slug, "whatsapp-uva-co")
        self.assertEqual(Channel.objects.filter(name="WhatsApp Colombia", business_unit__slug="uva").count(), 1)
