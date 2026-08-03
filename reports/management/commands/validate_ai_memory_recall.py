"""Comprueba que la recuperacion de memorias funciona en el motor de este entorno.

La busqueda usa `pg_trgm` en Postgres y un respaldo por palabras en SQLite. Los tests
corren en SQLite, asi que la rama de Postgres —la que de verdad usa produccion— no la
cubre ninguna prueba. Este comando la ejercita donde importa.

No deja rastro: crea una nota de prueba, consulta y la borra de verdad.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection

from reports.ai.memory import relevant_memories
from reports.models import AiMemory

NOTA = "Prueba de recuperacion: trabaja con la marca DistriSex al mayor"
CONSULTAS = [
    ("Como va DistriSex este mes?", True),
    ("distrisex mayorista", True),
    ("Cuantas webs hay en alerta?", False),
]


class Command(BaseCommand):
    help = "Verifica la busqueda de memorias de la IA en el motor actual."

    def handle(self, *args, **options):
        usuario = User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
        if not usuario:
            self.stdout.write(self.style.ERROR("No hay usuarios de staff para la prueba."))
            return

        self.stdout.write(f"Motor: {connection.vendor}")
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
                self.stdout.write(f"pg_trgm instalada: {bool(cursor.fetchone())}")

        nota = AiMemory.objects.create(user=usuario, content=NOTA)
        try:
            for consulta, deberia_encontrarla in CONSULTAS:
                encontradas = relevant_memories(usuario, consulta, limit=3)
                aparecio = any(m.pk == nota.pk for m in encontradas)
                # Sin coincidencia la busqueda devuelve las mas usadas, asi que aqui
                # solo importa el caso que si debe encontrarla.
                marca = "OK" if aparecio == deberia_encontrarla or not deberia_encontrarla else "FALLA"
                self.stdout.write(f"  [{marca}] '{consulta}' -> {len(encontradas)} notas, la de prueba: {aparecio}")
        finally:
            nota.delete()

        self.stdout.write(self.style.SUCCESS("Prueba terminada, la nota se borro."))
