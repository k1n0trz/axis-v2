"""Crea DistriSex como marca propia.

DistriSex es la operacion mayorista: vende el catalogo de Bali y de Uva juntos, a
mayoristas, con su propia tienda WooCommerce (distrisexcolombia.com) y su propia
facturacion en COP. La migracion 0023 habia borrado la unidad porque entonces no
tenia datos; ahora si los tiene.
"""
from django.db import migrations

SLUG = "distrisex"
CHANNELS = (
    ("Web mayorista", "ecommerce-distrisex", 1),
    ("WhatsApp mayorista", "whatsapp-distrisex", 2),
)


def crear_distrisex(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    Country = apps.get_model("reports", "Country")
    Channel = apps.get_model("reports", "Channel")

    unidad = BusinessUnit.objects.filter(slug=SLUG).first() or BusinessUnit.objects.filter(name__iexact="DistriSex").first()
    if unidad is None:
        siguiente = (BusinessUnit.objects.count() or 0) + 1
        unidad = BusinessUnit.objects.create(
            name="DistriSex",
            slug=SLUG,
            display_order=siguiente,
            is_active=True,
            description="Operacion mayorista: catalogo Bali y Uva vendido a mayoristas.",
        )
    else:
        unidad.slug = SLUG
        unidad.name = "DistriSex"
        unidad.is_active = True
        unidad.save(update_fields=["slug", "name", "is_active", "updated_at"])

    colombia = Country.objects.filter(code__iexact="CO").first() or Country.objects.filter(name__iexact="Colombia").first()
    if colombia is None:
        colombia = Country.objects.create(code="CO", name="Colombia", display_order=1, is_active=True)
    colombia.business_units.add(unidad)

    for nombre, slug, orden in CHANNELS:
        if not Channel.objects.filter(business_unit=unidad, slug=slug).exists():
            Channel.objects.create(
                business_unit=unidad,
                name=nombre,
                slug=slug,
                display_order=orden,
                is_active=True,
            )


def borrar_distrisex(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    BusinessUnit.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0055_seed_websites"),
    ]

    operations = [
        migrations.RunPython(crear_distrisex, borrar_distrisex),
    ]
