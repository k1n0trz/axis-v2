"""Reglas de campana -> categoria de Google Ads.

Contexto: la sincronizacion diaria corria con `google-category-rules.example.json`,
el archivo de muestra. Con esas reglas:

- Colombia perdia el gasto de las campanas que ninguna regla reconocia. La de
  "Covers" gasto 69.862 COP en 2026 y no llego a Axis.
- Ecuador y Mexico no perdian plata, pero el 100% y el 81% de su gasto entraba a
  copa-menstrual por un `fallback` silencioso, no por una regla.

El fallback era correcto para lo que ya paso: en su momento esas cuentas solo
tenian campanas de copa. El riesgo es hacia adelante, con una campana nueva.
"""
import json
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from reports.integrations.clients import load_json_mapping, match_rule
from reports.management.commands.fetch_google_ads import Command, fallback_uva_category
from reports.models import ProductCategory

RUTA_REGLAS = "docs/mappings/google-category-rules.json"


class ArchivoDeReglasTests(TestCase):
    def setUp(self):
        self.reglas = load_json_mapping(RUTA_REGLAS).get("rules", [])

    def test_el_archivo_real_existe_y_tiene_reglas(self):
        self.assertTrue(Path(RUTA_REGLAS).exists())
        self.assertGreater(len(self.reglas), 20)

    def test_las_categorias_referenciadas_son_exactamente_las_esperadas(self):
        """Fija el conjunto para que un slug mal escrito no pase inadvertido.

        No se compara contra la base: en una base limpia solo existen dos
        categorias (`cubrepezones` y `cubrepezones-sin-adhesivo`, creadas por
        migracion). Las demas nacen cuando un importador las necesita, asi que el
        catalogo real depende de lo que se haya importado. Un slug con un dedazo
        crearia una categoria nueva en silencio.
        """
        esperadas = {
            "almohadilla-colico-menstrual",
            "bolas-kegel-uva",
            "copa-menstrual",
            "cubrepezones",
            "dilatadores-vaginales",
            "disco-menstrual",
            "esterilizador-electrico-para-copas-menstruales",
            "hidratante-intimo-uva",
            "higiene-intima",
            "lubricantes",
            "panties-menstruales",
            "toallitas-compactas-uva",
        }
        self.assertEqual({r["category"] for r in self.reglas}, esperadas)

    def test_ninguna_regla_apunta_a_la_categoria_fusionada(self):
        """`cubrepezones-sin-adhesivo` quedo vacia e inactiva en la migracion 0052.

        Sigue existiendo como residuo, pero ninguna regla debe volver a mandarle
        gasto: eso reabriria una separacion que el negocio no quiere.
        """
        self.assertNotIn("cubrepezones-sin-adhesivo", {r["category"] for r in self.reglas})
        residuo = ProductCategory.objects.filter(slug="cubrepezones-sin-adhesivo").first()
        if residuo:
            self.assertFalse(residuo.is_active)

    def test_clasifica_las_campanas_reales_con_gasto(self):
        casos = [
            ("21/06/2024 | Ventas | Search | CO", "copa-menstrual"),
            ("14/11/25 | Ventas | Panties | PMax", "panties-menstruales"),
            ("07/04/26 | Ventas | PMax | Disco | CO", "disco-menstrual"),
            ("22/05/26 | Ventas | Search | Kegel", "bolas-kegel-uva"),
            ("11/06/26 | Ventas | PMax | Hidratante", "hidratante-intimo-uva"),
            # Esta es la que se perdia con el archivo de muestra.
            ("18/12/25 | Ventas | Pmax | Covers", "cubrepezones"),
            ("16/09/25 | PMax | Dilatadores | CO", "dilatadores-vaginales"),
            ("16/09/2025 | Ventas | Search | EC", "copa-menstrual"),
            ("30/01/26 | Ventas | Search | MX", "copa-menstrual"),
            ("07/07/26 | Ventas | Search | Disco | MX", "disco-menstrual"),
        ]
        for nombre, esperada in casos:
            with self.subTest(campana=nombre):
                self.assertEqual(match_rule(nombre, self.reglas), esperada)

    def test_lo_especifico_gana_a_lo_generico(self):
        # El orden del archivo importa: match_rule devuelve la primera coincidencia.
        self.assertEqual(match_rule("Ventas | Disco menstrual | CO", self.reglas), "disco-menstrual")

    def test_todo_cubrepezones_cae_en_una_sola_categoria(self):
        """Decision del negocio del 31-jul-2026: no se separa por adhesivo."""
        for nombre in ("18/12/25 | Ventas | Pmax | Covers", "Cubrepezones sin adhesivo CO",
                       "Ventas | Cubrepezones | CO", "Ventas | Sin adhesivos | CO"):
            with self.subTest(campana=nombre):
                self.assertEqual(match_rule(nombre, self.reglas), "cubrepezones")

    def test_el_despigmentante_no_se_mapea_a_proposito(self):
        """Producto descontinuado. Su gasto entra al total, no al desglose."""
        self.assertIsNone(match_rule("02/10/25 | Ventas | PMax | Despigmentante", self.reglas))

    def test_una_campana_nueva_de_ecuador_no_hereda_el_supuesto_de_copa(self):
        # Las genericas de EC/MX estan por nombre completo, no con comodin de pais.
        # Una campana nueva debe quedar sin regla para que alguien la mapee.
        self.assertIsNone(match_rule("01/08/26 | Ventas | Search | Calzones | EC", self.reglas))

    def test_el_archivo_es_json_valido_y_las_notas_no_estorban(self):
        datos = json.loads(Path(RUTA_REGLAS).read_text(encoding="utf-8"))
        self.assertIn("_notas", datos)
        self.assertTrue(all("match" in r and "category" in r for r in datos["rules"]))


class RastroDelFallbackTests(SimpleTestCase):
    def test_el_fallback_solo_aplica_a_ecuador_y_mexico(self):
        self.assertEqual(fallback_uva_category("EC"), "copa-menstrual")
        self.assertEqual(fallback_uva_category("MX"), "copa-menstrual")
        self.assertEqual(fallback_uva_category("CO"), "")

    def test_la_nota_dice_que_campanas_se_asignaron_por_defecto(self):
        nota = Command()._spend_note("6385600284", set(), {"01/08/26 | Ventas | Search | EC"})

        self.assertIn("Cuenta Google Ads 6385600284", nota)
        self.assertIn("asignadas por defecto", nota)
        self.assertIn("01/08/26 | Ventas | Search | EC", nota)

    def test_sin_campanas_raras_la_nota_queda_limpia(self):
        self.assertEqual(Command()._spend_note("7015245415", set(), set()), "Cuenta Google Ads 7015245415.")


class SyncDiarioTests(SimpleTestCase):
    def test_el_sync_usa_el_archivo_real_y_no_el_de_muestra(self):
        codigo = Path("reports/management/commands/sync_axis_daily_data.py").read_text(encoding="utf-8")

        self.assertIn('default="docs/mappings/google-category-rules.json"', codigo)
        self.assertNotIn("google-category-rules.example.json", codigo)
        # Las tres cuentas de Uva suman al total lo que ninguna regla clasifique.
        self.assertEqual(codigo.count('"--count-unmapped-spend"'), 3)


class SoloSeAnotaLoQueGastoTests(SimpleTestCase):
    """Una campana apagada no debe ensuciar la nota de cada dia.

    La primera version anotaba cualquier campana que cayera al fallback, con gasto
    o sin el. Mexico tiene cuatro campanas apagadas, asi que la nota decia
    "asignadas por defecto" todos los dias sin que hubiera nada que revisar.
    """

    def test_el_codigo_condiciona_la_anotacion_al_gasto(self):
        codigo = Path("reports/management/commands/fetch_google_ads.py").read_text(encoding="utf-8")

        self.assertIn("if category_slug and spend_cop > 0:", codigo)
        self.assertIn("if spend_cop > 0:\n                            unmapped_campaigns.add", codigo)
