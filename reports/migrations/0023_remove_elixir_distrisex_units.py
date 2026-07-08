from django.db import migrations


def remove_elixir_distrisex_units(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    BusinessUnit.objects.filter(slug__in=["elixir", "distri-sex"]).delete()
    BusinessUnit.objects.filter(name__iexact="Elixir").delete()
    BusinessUnit.objects.filter(name__iexact="DistriSex").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0022_grant_editrafficker_bali_permissions"),
    ]

    operations = [
        migrations.RunPython(remove_elixir_distrisex_units, migrations.RunPython.noop),
    ]
