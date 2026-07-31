#!/usr/bin/env python
import os
import sys


def main():
    # La suite usa su propio modulo de settings, que vacia las credenciales
    # externas. Sin esto los tests salen a internet con las credenciales reales
    # del .env: un test que renderizaba /uva/ llamaba a Meta Ads de verdad.
    # Se puede forzar otro modulo exportando DJANGO_SETTINGS_MODULE.
    por_defecto = "config.settings.test" if "test" in sys.argv[1:2] else "config.settings.development"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", por_defecto)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

