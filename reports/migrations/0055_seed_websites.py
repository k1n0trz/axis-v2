"""Siembra las webs monitoreadas.

Antes esto pasaba en cada GET de /webs/ con `update_or_create`, asi que la
pagina escribia 4 filas por carga y revertia cualquier edicion hecha en el
admin. La siembra pertenece al despliegue, no al render.
"""
from django.db import migrations

SEED_ROWS = [
    ("copa-uva-colombia", "Copa Uva", "Colombia", "https://copauva.com/", "wordpress", 10),
    ("copa-uva-ecuador", "Copa Uva", "Ecuador", "https://copauva.com/ec/", "wordpress", 20),
    ("copa-uva-mexico", "Copa Uva", "Mexico", "https://uvawomen.mx/", "wordpress", 30),
    ("bali-sex-store-colombia", "Bali Sex Store", "Colombia", "https://balisexstore.com/", "shopify", 40),
]


def seed_websites(apps, schema_editor):
    Website = apps.get_model("reports", "Website")
    # Compatibilidad con el slug antiguo de Bali antes de crear el nuevo.
    antiguo = Website.objects.filter(slug="bali-sex-store-mexico").first()
    if antiguo and not Website.objects.filter(slug="bali-sex-store-colombia").exists():
        antiguo.slug = "bali-sex-store-colombia"
        antiguo.country_label = "Colombia"
        antiguo.save(update_fields=["slug", "country_label", "updated_at"])

    for slug, name, country_label, url, platform, display_order in SEED_ROWS:
        Website.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "country_label": country_label,
                "url": url,
                "platform": platform,
                "stage": "active",
                "display_order": display_order,
                "monitor_enabled": True,
                "notes": "",
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0054_align_marketplace_inventory_index_names"),
    ]

    operations = [
        migrations.RunPython(seed_websites, migrations.RunPython.noop),
    ]
