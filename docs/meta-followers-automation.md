# Automatizacion de Seguidores Meta

## Diagnostico corto

- La consulta de Meta Marketing API via `insights` si nos devuelve gasto por adset y categorias de producto.
- En las campanas de seguidores/visitas al perfil, la API no esta exponiendo de forma estable `Seguidores de Instagram` ni un `action_type` consistente para seguidores nuevos.
- En el export CSV de Ads Manager si aparecen claramente:
  - `Resultados`
  - `Indicador de resultado`
  - `Visitas al perfil de Instagram`
  - `Seguidores de Instagram`
- Con base en esa evidencia, el flujo principal recomendado para `Seguidores Awn Internacional` es consumir automaticamente los CSV programados por correo.

## Flujo principal

1. Meta Ads Manager envia un reporte CSV programado al correo.
2. Axis revisa el buzon IMAP configurado.
3. Axis descarga adjuntos `.csv`.
4. Axis detecta filas donde `Indicador de resultado = profile_visit_view`.
5. Axis calcula:
   - `instagram_profile_visits = Resultados`
   - `new_followers = Seguidores de Instagram`
   - `cpr = spend_amount / instagram_profile_visits`
   - `cps = spend_amount / new_followers`
6. Axis guarda el consolidado diario por pais en `Seguidores Awn Internacional`.

## Variables .env

```env
META_REPORTS_IMAP_HOST=
META_REPORTS_IMAP_PORT=993
META_REPORTS_IMAP_USERNAME=
META_REPORTS_IMAP_PASSWORD=
META_REPORTS_IMAP_FOLDER=INBOX
META_REPORTS_IMAP_SUBJECT_FILTER=Meta Ads
META_REPORTS_IMAP_FROM_FILTER=
META_REPORTS_DOWNLOAD_DIR=data/meta-reports
```

## Comando principal

```bash
python manage.py fetch_meta_followers_email_reports
```

Opciones utiles:

```bash
python manage.py fetch_meta_followers_email_reports --all
python manage.py fetch_meta_followers_email_reports --subject-filter "UVA-ECUADOR"
python manage.py fetch_meta_followers_email_reports --from-filter "noreply@facebookmail.com"
```

## Respaldo manual

```bash
python manage.py import_meta_followers_csv "C:/ruta/reporte.csv" --country EC
python manage.py import_meta_followers_csv "C:/ruta/reporte.csv" --country MX
```

## Como programar el reporte en Meta

- Nivel: `Conjuntos de anuncios`
- Rango: `Diario`
- Formato: `CSV`
- Columnas minimas:
  - `Resultados`
  - `Indicador de resultado`
  - `Visitas al perfil de Instagram`
  - `Seguidores de Instagram`
  - `Importe gastado`
  - `Nombre del conjunto de anuncios`
  - `Inicio del informe`
  - `Fin del informe`
- Enviar al correo operativo que Axis pueda leer por IMAP.

## Recomendacion operativa

- Usar una cuenta de correo dedicada para estos reportes.
- Crear un filtro o carpeta solo para Meta reportes.
- Ejecutar este comando a diario por Celery Beat o cron despues de la hora de envio del reporte.
