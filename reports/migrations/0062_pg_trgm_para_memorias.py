"""Habilita pg_trgm: la busqueda de memorias compara por similitud.

`CreateExtension` se salta sola en motores que no son Postgres, asi que la base de
pruebas en SQLite no se entera. La recuperacion de memorias tiene su propio respaldo
por palabras para ese caso.
"""
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("reports", "0061_ai_memory")]

    operations = [TrigramExtension()]
