from django.db import migrations


def seed_bali_physical_store(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    Channel = apps.get_model("reports", "Channel")
    Country = apps.get_model("reports", "Country")

    bali, _ = BusinessUnit.objects.get_or_create(
        slug="bali",
        defaults={"name": "Bali", "display_order": 2, "is_active": True},
    )
    country, _ = Country.objects.get_or_create(
        code="CO",
        defaults={"name": "Colombia", "display_order": 1, "is_active": True},
    )
    country.business_units.add(bali)
    Channel.objects.update_or_create(
        business_unit=bali,
        slug="bali-tienda-fisica",
        defaults={"name": "Tienda Fisica", "display_order": 4, "is_active": True},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0032_roastrafficlightsetting"),
    ]

    operations = [
        migrations.CreateModel(
            name="BaliPhysicalStoreSale",
            fields=[],
            options={
                "verbose_name": "Tienda Fisica Bali",
                "verbose_name_plural": "Tienda Fisica Bali",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("reports.dailychannelsale",),
        ),
        migrations.RunPython(seed_bali_physical_store, migrations.RunPython.noop),
    ]
