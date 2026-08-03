"""Canal para las muestras que se envian a creadoras UGC.

En la hoja de Ecuador hay 22 filas con CENTRO DE COSTOS = "Publicidad" y precio 0: son
productos entregados a creadoras para que hagan contenido. No son ventas, pero tampoco
son nada: hoy el importador las descartaba en silencio porque ese canal no existia, asi
que las unidades entregadas no quedaban registradas en ninguna parte.
"""
from django.db import migrations

SLUG = "ugc-muestras-uva"


def create_channel(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    Channel = apps.get_model("reports", "Channel")
    uva = BusinessUnit.objects.filter(slug="uva").first()
    if uva and not Channel.objects.filter(business_unit=uva, slug=SLUG).exists():
        Channel.objects.create(
            business_unit=uva,
            name="Muestras UGC",
            slug=SLUG,
            display_order=90,
            is_active=True,
        )


def remove_channel(apps, schema_editor):
    apps.get_model("reports", "Channel").objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [("reports", "0057_integration_run")]
    operations = [migrations.RunPython(create_channel, remove_channel)]
