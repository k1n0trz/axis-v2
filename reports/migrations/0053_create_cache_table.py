"""Crea la tabla que respalda la cache compartida entre workers e instancias."""
from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    table = getattr(settings, "CACHE_TABLE_NAME", "axis_cache")
    # createcachetable es idempotente: no hace nada si la tabla ya existe.
    call_command("createcachetable", table, database=schema_editor.connection.alias, verbosity=0)


def drop_cache_table(apps, schema_editor):
    table = getattr(settings, "CACHE_TABLE_NAME", "axis_cache")
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS "{table}"')


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0052_merge_cubrepezones_categories"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
