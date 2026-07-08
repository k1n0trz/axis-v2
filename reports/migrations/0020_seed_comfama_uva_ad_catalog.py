from django.db import migrations


def seed_comfama_catalog(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    BusinessUnit.objects.update_or_create(
        slug="comfama-uva",
        defaults={"name": "Comfama Uva", "display_order": 2, "is_active": True},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0019_allow_category_sale_returns"),
    ]

    operations = [
        migrations.RunPython(seed_comfama_catalog, migrations.RunPython.noop),
    ]
