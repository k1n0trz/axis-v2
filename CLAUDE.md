# Axis

Tablero interno de Helti: consolida ventas, inversión publicitaria y métricas de las
marcas **Uva** (Colombia, Ecuador, México), **Bali**, **DistriSex** (mayorista) y
**Marketplace**. Django 6 sobre Cloud Run + Cloud SQL.

## Convenciones

**Identificadores en inglés, prosa en español.** Clases, funciones, parámetros,
variables y claves de payload JSON en inglés. Comentarios, docstrings, mensajes al
usuario y **nombres de tests** en español. No es un accidente: es consistente en todo
el proyecto.

```python
def parse_decimal(value, default=ZERO):
    """Convierte a Decimal un valor de hoja de calculo."""
    # Una fila rara no debe tumbar la importacion del dia.
```

```python
def test_una_cantidad_con_coma_decimal_no_se_multiplica_por_diez(self):
```

Los comentarios explican **por qué**, no qué. La mayoría documentan un incidente real:
si un comentario dice que algo se contaba dos veces, es porque pasó.

## Cómo correr las cosas

```bash
python manage.py test reports          # usa config.settings.test automaticamente
python manage.py runserver
python manage.py ensure_axis_catalogs  # siembra unidades, paises, canales, plataformas
```

`manage.py test` cambia solo a `config.settings.test`, que **vacía todas las
credenciales externas**. Sin eso los tests salen a internet con las credenciales
reales del `.env`: había uno que llamaba a la API de Meta y esperaba 18 segundos. Un
test que ejercite una integración lo declara con `override_settings` y un mock.

## Reglas que no son obvias

**Una página no escribe en la base.** Hubo `ensure_*_catalogs()` y `seed_websites()`
dentro de los renders, con `update_or_create`: cada GET hacía hasta 10 escrituras,
reescribía `updated_at` en cada visita y revertía lo que el equipo editaba en el admin.
`reports/tests/test_read_only_gets.py` lo fija para nueve rutas.

**Nada bloqueante de red en el camino de la página.** El panel de Meta tardaba 16 s con
la caché fría. Ahora la vista solo lee caché y el navegador pide el panel aparte.

**Los números de Excel se leen con `reports/utils/numbers.py`.** Nunca
`str(v).replace(",", "")`: eso convertía `"16,72"` en `1672`. Había cinco copias de esa
función y por eso el mismo bug hubo que arreglarlo dos veces.

**Idempotencia en los importadores.** Todos usan `update_or_create` sobre una clave
única real. Correr dos veces el mismo día no debe duplicar nada.

**Los importadores avisan, no corrigen.** Si la fuente viene rara —`VALOR` con el total
de la línea en vez del precio unitario— se reporta y se sigue. Corregir en el
importador hace que el archivo fuente y Axis digan cosas distintas y nadie sepa cuál
creer.

**Un fallo de una fuente externa no borra el dato bueno.** Si PageSpeed o Meta no
responden, se conserva la última medición y se marca como `stale` en vez de escribir
ceros o nulos encima.

## Estructura

```
config/settings/{base,development,production,test}.py
reports/
  services/
    sales_dashboard.py    constructores de tablero (grande; se esta partiendo)
    common.py             piezas compartidas: ZERO, safe_ratio, parse_excel_date...
    meta_ads_panel.py     panel de anuncios de Meta
    geo_maps.py           mapas y metricas por region
    website_monitor.py    diagnostico de webs
  integrations/
    clients.py            clientes HTTP (Meta, Google Ads, WooCommerce, Shopify...)
    run_log.py            bitacora de ejecuciones: track_run()
  management/commands/    ~50 comandos; sync_axis_daily_data orquesta el dia
  utils/numbers.py        lectura de numeros de hoja de calculo
docs/mappings/            reglas campana -> categoria (el .json real, no el .example)
```

`sales_dashboard.py` viene de 3.726 líneas. Para partirlo: verificar primero que el
bloque no tenga referencias de vuelta, mover lo que comparte a `common.py`, y
comprobar con el AST que el módulo nuevo no deja nombres sueltos. Las pruebas parchean
donde el objeto **se usa**, así que mover código obliga a mover los `patch(...)`.

## Despliegue

Tres artefactos separados en Cloud Run, cada uno con **su propia imagen fijada y su
propia configuración de entorno**: el servicio `axis-temp` y los jobs
`axis-temp-sync-daily`, `axis-temp-warm-meta-preview`, `axis-temp-websites-health`.

**Actualizar el servicio no actualiza los jobs, y agregar una variable al servicio no
la agrega a los jobs.** Las importaciones corren en los jobs, así que desplegar solo el
servicio cambia el tablero y deja los datos entrando con código viejo.

```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/<proyecto>/cloud-run-source-deploy/axis-temp:<tag> .
# actualizar el job de sync, aplicar migraciones, y despues el servicio y los otros jobs
gcloud run jobs execute axis-temp-sync-daily --args="manage.py,migrate,--noinput"
```

`--args` separa por comas: un `manage.py shell -c` con comas en el código se parte.
No usar `bootstrap_cloudsql` para migrar — además de `migrate` hace `loaddata`.

## Secretos

Todo por entorno, nada en el código. `.env` está en `.gitignore` y nunca ha estado en
el historial. Las credenciales reales viven en Secret Manager; `.env.example`
documenta cada variable y por qué importa. `validate_axis_integrations` dice qué
fuentes están listas sin exponer valores.
