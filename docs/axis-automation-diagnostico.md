# Diagnostico y roadmap de automatizacion Axis

## 1. Estado actual del sistema

Axis ya tiene una base funcional importante para este proyecto:

- Modelos diarios para ventas por canal, ventas por categoria, inversion diaria, metricas por categoria, seguidores de Awn Internacional y modulo Bali.
- Importadores existentes para Colombia, Mexico, Ecuador, Bali e Instagram basados en Excel.
- Utilidad de OneDrive mediante Microsoft Graph en `C:\axis-v2\reports\utils\onedrive.py`.
- Comandos de management que ya usan `update_or_create`, lo cual reduce el riesgo de duplicados.

Conclusiones:

- El cuello de botella actual no es Axis como tal, sino la dependencia de consulta manual en WooCommerce, Meta Ads, Google Ads, Shopify y Excels compartidos.
- La estructura de datos en Axis soporta casi todo el flujo descrito.
- El proyecto se debe enfocar en reemplazar entradas manuales por una capa de integraciones y una orquestacion diaria.

## 2. Hallazgos por etapa del proceso

### Etapa 1: ventas diarias e inversion diaria

- Colombia web ya puede automatizarse directo desde WooCommerce.
- WhatsApp depende de Excel en OneDrive, por lo que la automatizacion correcta es Microsoft Graph + lectura del workbook.
- Mexico y Ecuador ya tienen importadores por Excel, pero conviene migrar Mexico web a API de WooCommerce y dejar Ecuador sobre Graph/Excel mientras el area comercial siga operando asi.
- La conversion USD/MXN a COP no debe seguir manual. Axis ya guarda `original_amount`, `original_currency` y `exchange_rate`, por lo que la conversion encaja naturalmente.
- Inversion diaria por pais y plataforma puede cargarse en `DailyAdSpend`.

### Etapa 2: ventas por categoria y canal

- Axis ya tiene `DailyProductCategorySale`.
- Colombia y Mexico pueden salir desde WooCommerce si existe un mapeo producto -> categoria Axis.
- Ecuador sigue requiriendo Excel hasta que la fuente original cambie.

### Etapa 3: metricas por categoria e Instagram

- Axis ya tiene `DailyProductCategoryMetric`.
- Meta Ads y Google Ads pueden entregar gasto y conversiones por campana.
- Para que el dato sea estable, se necesita un archivo de reglas que diga que campañas pertenecen a cada categoria.
- En Instagram/Awn, el CPS no debe calcularse manualmente: `cps = spend_amount / new_followers`.

### Etapa 4: Bali

- Axis ya tiene `BaliDailyMetric` y `BaliCommunityWebcamMetric`.
- Falta automatizar Shopify y Google Ads Bali.
- El total acumulado de suscriptores de comunidad webcam deberia calcularse automaticamente en backend; hoy el usuario lo digita a mano.

## 3. Ajustes recomendados en Axis

### Ajustes prioritarios

1. Crear una carpeta de integraciones reutilizable.
   Ya se dejo base en `C:\axis-v2\reports\integrations`.

2. Guardar reglas de mapeo fuera del codigo.
   Recomendado:
   - `docs/mappings/meta-category-rules.json`
   - `docs/mappings/google-category-rules.json`
   - `docs/mappings/woocommerce-product-map.json`
   - `docs/mappings/onedrive-column-map.json`

3. Automatizar el total de comunidad webcam Bali.
   Recomendacion: calcular el acumulado tomando el ultimo registro + `new_subscribers`.

4. Añadir bitacora de ejecuciones.
   Idealmente crear en una siguiente fase un modelo `IntegrationRun` con:
   - fuente
   - fecha objetivo
   - estado
   - resumen
   - errores
   - payload resumido

5. Separar credenciales por pais y fuente.
   No mezclar una sola cuenta o token para todo.

## 4. Credenciales y configuracion requerida

### Microsoft Graph / OneDrive

Ya existe una app de Azure AD registrada en `C:\axis-v2\docs\apis-microsoft.txt`.

Datos utiles encontrados:

- `ONEDRIVE_CLIENT_ID`: ya disponible en ese archivo.
- `ONEDRIVE_TENANT_ID`: ya disponible en ese archivo.
- `ONEDRIVE_CLIENT_SECRET`: ya disponible en ese archivo.

Recomendaciones:

- Mover el secreto a `.env`.
- Si este repo o workspace se comparte, rotar ese secreto.
- Solicitar permisos de app para Microsoft Graph:
  - `Files.Read.All`
  - `Sites.Read.All`
  - `User.Read.All`

Tambien necesitas definir:

- `ONEDRIVE_USER_ID`
- `ONEDRIVE_WHATSAPP_FILE_PATH`
- `ONEDRIVE_ECUADOR_FILE_PATH`

### WooCommerce

Por cada tienda:

- base URL
- consumer key
- consumer secret

Variables esperadas:

- `WOOCOMMERCE_CO_BASE_URL`
- `WOOCOMMERCE_CO_CONSUMER_KEY`
- `WOOCOMMERCE_CO_CONSUMER_SECRET`
- `WOOCOMMERCE_MX_BASE_URL`
- `WOOCOMMERCE_MX_CONSUMER_KEY`
- `WOOCOMMERCE_MX_CONSUMER_SECRET`

### Meta Ads

Necesitas:

- `META_ACCESS_TOKEN`
- `META_API_VERSION`
- `META_CO_ACCOUNT_ID`
- `META_MX_ACCOUNT_ID`
- `META_EC_ACCOUNT_ID`

Adicionalmente debes definir reglas de clasificacion de campañas por categoria.

### Google Ads

Necesitas:

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CLIENT_ID`
- `GOOGLE_ADS_CLIENT_SECRET`
- `GOOGLE_ADS_REFRESH_TOKEN`
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
- `GOOGLE_ADS_CO_CUSTOMER_ID`
- `GOOGLE_ADS_MX_CUSTOMER_ID`
- `GOOGLE_ADS_EC_CUSTOMER_ID`
- `GOOGLE_ADS_BALI_CUSTOMER_ID`

### Shopify Bali

Necesitas:

- `SHOPIFY_BALI_SHOP_DOMAIN`
- `SHOPIFY_BALI_ACCESS_TOKEN`

### Conversion de divisas

Necesitas:

- `EXCHANGE_RATE_API_URL`
- `EXCHANGE_RATE_API_KEY`

## 5. Scripts generados

Se dejaron comandos iniciales en Django:

- `python manage.py fetch_woocommerce_sales`
- `python manage.py fetch_onedrive_excel`
- `python manage.py fetch_meta_ads`
- `python manage.py fetch_google_ads`
- `python manage.py convert_axis_currency`
- `python manage.py sync_axis_daily_data`

Y una capa compartida en:

- `C:\axis-v2\reports\integrations\clients.py`
- `C:\axis-v2\reports\integrations\schema.py`
- `C:\axis-v2\reports\integrations\axis_sync.py`

## 6. Estructura sugerida del .env

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=

ONEDRIVE_CLIENT_ID=
ONEDRIVE_CLIENT_SECRET=
ONEDRIVE_TENANT_ID=
ONEDRIVE_REDIRECT_URI=
ONEDRIVE_USER_ID=
ONEDRIVE_WHATSAPP_FILE_PATH=
ONEDRIVE_ECUADOR_FILE_PATH=

WOOCOMMERCE_CO_BASE_URL=
WOOCOMMERCE_CO_CONSUMER_KEY=
WOOCOMMERCE_CO_CONSUMER_SECRET=
WOOCOMMERCE_MX_BASE_URL=
WOOCOMMERCE_MX_CONSUMER_KEY=
WOOCOMMERCE_MX_CONSUMER_SECRET=

META_ACCESS_TOKEN=
META_API_VERSION=v20.0
META_CO_ACCOUNT_ID=
META_MX_ACCOUNT_ID=
META_EC_ACCOUNT_ID=

GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_REFRESH_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=
GOOGLE_ADS_CO_CUSTOMER_ID=
GOOGLE_ADS_MX_CUSTOMER_ID=
GOOGLE_ADS_EC_CUSTOMER_ID=
GOOGLE_ADS_BALI_CUSTOMER_ID=

SHOPIFY_BALI_SHOP_DOMAIN=
SHOPIFY_BALI_ACCESS_TOKEN=

EXCHANGE_RATE_API_URL=https://api.exchangerate.host
EXCHANGE_RATE_API_KEY=
```

## 7. Como usar las credenciales correctamente

### WooCommerce

- Nunca hardcodear claves en el codigo.
- Cada tienda debe tener sus claves propias.
- Usar permisos de solo lectura si no necesitas escribir pedidos.

### Microsoft Graph

- Usar app registration con permisos minimos necesarios.
- Para automatizacion sin login humano, preferir permisos de aplicacion con `client credentials`.

### Meta Ads y Google Ads

- Guardar tokens en `.env`.
- Programar rotacion o procedimiento de renovacion documentado.
- Registrar claramente que cuenta de anuncios corresponde a cada pais.

### API de divisas

- Convertir con fecha del registro, no con tasa del dia de ejecucion si estas reprocesando historicos.

## 8. Pruebas antes de automatizar

Orden recomendado:

1. Validar acceso a cada API por separado.
2. Ejecutar cada comando sin `--sync-axis`.
3. Revisar el JSON de salida y comparar contra el dato manual del mismo dia.
4. Ejecutar con `--sync-axis` en un rango pequeno o en base local.
5. Revisar que no existan duplicados ni montos inconsistentes.
6. Repetir la misma corrida para confirmar idempotencia.

Comandos de ejemplo:

```bash
python manage.py fetch_woocommerce_sales --date 2026-05-11 --country CO
python manage.py fetch_onedrive_excel --date 2026-05-11 --country CO --drive-path "Ventas/Whatsapp.xlsx"
python manage.py fetch_meta_ads --date 2026-05-11 --country CO --rules docs/mappings/meta-category-rules.json
python manage.py fetch_google_ads --date 2026-05-11 --country CO --rules docs/mappings/google-category-rules.json
python manage.py convert_axis_currency 120 --from-currency USD --to-currency COP
python manage.py sync_axis_daily_data --date 2026-05-11 --dry-run
```

## 9. Celery vs cron jobs

### Recomendacion principal

Usar Celery + Celery Beat cuando el proyecto pase a produccion operativa completa.

Motivos:

- Reintentos automaticos
- mejor trazabilidad
- separacion por tareas
- control de errores por fuente
- posibilidad de reprocesar dias especificos

### Cron jobs

Cron puede servir solo como fase transitoria si:

- el despliegue es simple
- no necesitas cola distribuida
- el volumen es bajo

### Tareas candidatas para Celery Beat

- `sync_woocommerce_co_daily`
- `sync_woocommerce_mx_daily`
- `sync_onedrive_whatsapp_daily`
- `sync_onedrive_ecuador_daily`
- `sync_meta_ads_daily`
- `sync_google_ads_daily`
- `sync_shopify_bali_daily`
- `sync_instagram_awn_daily`
- `sync_exchange_rates_daily`
- `reconcile_axis_daily`

## 10. Roadmap detallado

### Fase 0. Descubrimiento y mapeo

- Duracion estimada: 2 a 4 dias
- Confirmar cuentas, IDs, archivos, hojas y columnas reales.
- Construir mapeo producto -> categoria.
- Construir mapeo campaña -> categoria.

Entregables:

- inventario de credenciales
- mapping files
- matriz de fuentes por pais

### Fase 1. Accesos tecnicos y pruebas unitarias de conectividad

- Duracion estimada: 2 a 3 dias
- Validar Graph, WooCommerce, Meta Ads, Google Ads, Shopify y API FX.

Entregables:

- `.env` completo
- pruebas de conectividad por fuente
- comandos base funcionando sin persistencia

### Fase 2. Normalizacion de datos

- Duracion estimada: 3 a 5 dias
- Convertir cada fuente al esquema Axis.
- Completar reglas para categoria, moneda y pais.

Entregables:

- salidas JSON normalizadas
- comparativo manual vs automatico

### Fase 3. Persistencia segura en Axis

- Duracion estimada: 3 a 4 dias
- Conectar normalizadores con `DailyChannelSale`, `DailyProductCategorySale`, `DailyAdSpend`, `DailyProductCategoryMetric`, `AwnInternationalFollowerMetric` y `BaliDailyMetric`.
- Garantizar idempotencia y manejo de reprocesos.

Entregables:

- sincronizacion real sobre base de desarrollo
- pruebas de duplicado y consistencia

### Fase 4. Bali e Instagram

- Duracion estimada: 2 a 4 dias
- Automatizar Shopify Bali, Google Ads Bali y seguidores Awn.
- Eliminar calculos manuales de CPS y acumulados.

Entregables:

- flujo Bali automatizado
- flujo Awn automatizado

### Fase 5. Orquestacion diaria

- Duracion estimada: 2 a 3 dias
- Montar Celery/Beat o cron temporal.
- Agregar alertas por error y resumen diario.

Entregables:

- ejecucion automatica diaria
- alertas
- checklist de soporte

### Fase 6. Hardening y operacion

- Duracion estimada: 2 a 3 dias
- Auditoria de secretos
- rotacion de tokens
- documentacion final
- tablero de estado de integraciones

Entregables:

- operacion estable
- runbook tecnico
- plan de soporte

## 11. Tiempo total estimado

- MVP operativo parcial: 2 a 3 semanas
- Automatizacion completa con Bali, Instagram, Celery y hardening: 4 a 6 semanas

## 12. Lo que necesitas poner de tu parte

1. Confirmar las cuentas reales por pais en Meta Ads y Google Ads.
2. Confirmar rutas exactas de archivos en OneDrive y nombres de hojas.
3. Entregar llaves de WooCommerce y Shopify.
4. Definir el mapeo de campañas por categoria.
5. Definir si la automatizacion final vivira con Celery o cron temporal.
6. Confirmar si Ecuador seguira saliendo desde Excel o si hay otra fuente futura.
