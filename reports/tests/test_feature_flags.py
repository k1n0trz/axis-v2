"""El modulo de Tareas y Metas se controla por entorno, no editando codigo.

Estaba escrito a mano como `FEATURE_TASKS_GOALS_ENABLED = False` en views.py, asi
que encenderlo exigia editar el codigo y desplegar. El valor por defecto no cambia:
sigue apagado.

No se borra el modulo: son 8 modelos, 8 migraciones y ~1.100 lineas de plantillas
que el equipo construyo. Borrarlo es una decision de producto.
"""
from importlib import reload

from django.contrib.auth.models import User
from django.test import TestCase


class FeatureFlagTareasMetasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="analista", password="secreto", is_staff=True)
        self.client.force_login(self.user)

    def test_apagado_por_defecto(self):
        from reports import views

        self.assertFalse(views.FEATURE_TASKS_GOALS_ENABLED)

    def test_apagado_las_paginas_devuelven_404(self):
        self.assertEqual(self.client.get("/tareas/").status_code, 404)
        self.assertEqual(self.client.get("/metas/").status_code, 404)

    def test_apagado_la_barra_lateral_no_los_ofrece(self):
        html = self.client.get("/").content.decode("utf-8", "ignore")

        self.assertNotIn('href="/tareas/"', html)
        self.assertNotIn('href="/metas/"', html)

    def test_el_valor_se_lee_del_entorno(self):
        # Con la variable puesta, recargar el modulo lo enciende: no hace falta
        # tocar el codigo ni desplegar.
        import os

        from reports import views

        anterior = os.environ.get("FEATURE_TASKS_GOALS_ENABLED")
        os.environ["FEATURE_TASKS_GOALS_ENABLED"] = "True"
        try:
            reload(views)
            self.assertTrue(views.FEATURE_TASKS_GOALS_ENABLED)
        finally:
            if anterior is None:
                os.environ.pop("FEATURE_TASKS_GOALS_ENABLED", None)
            else:
                os.environ["FEATURE_TASKS_GOALS_ENABLED"] = anterior
            reload(views)
        self.assertFalse(views.FEATURE_TASKS_GOALS_ENABLED)
