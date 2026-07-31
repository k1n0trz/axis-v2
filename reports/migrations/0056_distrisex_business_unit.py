"""Crea DistriSex como marca propia.

DistriSex es la operacion mayorista: vende el catalogo de Bali y de Uva juntos, a
mayoristas, con su propia tienda WooCommerce (distrisexcolombia.com) y su propia
facturacion en COP. La migracion 0023 habia borrado la unit porque entonces no
tenia datos; ahora si los tiene.
"""
from django.db import migrations

SLUG = "distrisex"
CHANNELS = (
    ("Web mayorista", "ecommerce-distrisex", 1),
    ("WhatsApp mayorista", "whatsapp-distrisex", 2),
)


def create_distrisex(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    Country = apps.get_model("reports", "Country")
    Channel = apps.get_model("reports", "Channel")

    unit = BusinessUnit.objects.filter(slug=SLUG).first() or BusinessUnit.objects.filter(name__iexact="DistriSex").first()
    if unit is None:
        next_order = (BusinessUnit.objects.count() or 0) + 1
        unit = BusinessUnit.objects.create(
            name="DistriSex",
            slug=SLUG,
            display_order=next_order,
            is_active=True,
            description="Operacion mayorista: catalogo Bali y Uva vendido a mayoristas.",
        )
    else:
        unit.slug = SLUG
        unit.name = "DistriSex"
        unit.is_active = True
        unit.save(update_fields=["slug", "name", "is_active", "updated_at"])

    colombia = Country.objects.filter(code__iexact="CO").first() or Country.objects.filter(name__iexact="Colombia").first()
    if colombia is None:
        colombia = Country.objects.create(code="CO", name="Colombia", display_order=1, is_active=True)
    colombia.business_units.add(unit)

    for name, slug, display_order in CHANNELS:
        if not Channel.objects.filter(business_unit=unit, slug=slug).exists():
            Channel.objects.create(
                business_unit=unit,
                name=name,
                slug=slug,
                display_order=display_order,
                is_active=True,
            )


def remove_distrisex(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    BusinessUnit.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0055_seed_websites"),
    ]

    operations = [
        migrations.RunPython(create_distrisex, remove_distrisex),
    ]
