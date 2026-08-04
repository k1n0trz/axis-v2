# Exportación segura de autenticación de Mercado Libre

Este procedimiento crea un `.env` local sin imprimir los secretos en pantalla. El proyecto fuente es `sylvan-cycle-487021-f7` y la región es `us-central1`.

El paquete contiene dos perfiles de nombres:

- `MERCADOLIBRE_*`: credenciales usadas por Axis ML Data.
- `MELI_*`: credenciales usadas por Auditor (`analizador-catalogo-test`).

No existe un `MERCADOLIBRE_REFRESH_TOKEN` ni un `MERCADOLIBRE_ACCESS_TOKEN` persistido en Cloud Run o Secret Manager. Axis obtiene un access token transitorio con `grant_type=client_credentials`. Si el MCP local exige un refresh token, será necesario completar su flujo OAuth de autorización en la máquina destino.

## Windows PowerShell

Ejecutar en la máquina destino desde la carpeta privada del MCP:

```powershell
$ErrorActionPreference = "Stop"
$ProjectId = "sylvan-cycle-487021-f7"
$Region = "us-central1"
$AuditorServiceName = "analizador-catalogo-test"
$EnvPath = Join-Path (Get-Location) ".env.mercadolibre"

gcloud auth login
gcloud config set project $ProjectId

$AxisClientId = (gcloud secrets versions access latest --project=$ProjectId --secret="axis-mercadolibre-client-id")
$AxisClientSecret = (gcloud secrets versions access latest --project=$ProjectId --secret="axis-mercadolibre-client-secret")
$AuditorClientSecret = (gcloud secrets versions access latest --project=$ProjectId --secret="analizador-catalogo-test-meli-client-secret")
$AuditorPublicKey = (gcloud secrets versions access latest --project=$ProjectId --secret="analizador-catalogo-test-meli-public-key")

$AuditorService = gcloud run services describe $AuditorServiceName --region=$Region --project=$ProjectId --format=json | ConvertFrom-Json
$AuditorEnv = @($AuditorService.spec.template.spec.containers[0].env)
$AuditorClientId = [string](($AuditorEnv | Where-Object name -eq "MELI_CLIENT_ID" | Select-Object -First 1).value)
$MercadoLibreApiUrl = [string](($AuditorEnv | Where-Object name -eq "MERCADOLIBRE_API_URL" | Select-Object -First 1).value)
$MercadoLibreSiteId = [string](($AuditorEnv | Where-Object name -eq "MERCADOLIBRE_SITE_ID" | Select-Object -First 1).value)
$MeliApiUrl = [string](($AuditorEnv | Where-Object name -eq "MELI_API_URL" | Select-Object -First 1).value)

function ConvertTo-DotEnvValue([string]$Value) {
    if ($null -eq $Value) { return '""' }
    return '"' + $Value.Replace('\\', '\\\\').Replace('"', '\"').Replace("`r", '').Replace("`n", '\n') + '"'
}

$Lines = @(
    "# Axis ML Data"
    "MERCADOLIBRE_CLIENT_ID=$(ConvertTo-DotEnvValue $AxisClientId)"
    "MERCADOLIBRE_CLIENT_SECRET=$(ConvertTo-DotEnvValue $AxisClientSecret)"
    "MERCADOLIBRE_API_URL=$(ConvertTo-DotEnvValue $MercadoLibreApiUrl)"
    "MERCADOLIBRE_SITE_ID=$(ConvertTo-DotEnvValue $MercadoLibreSiteId)"
    ""
    "# Auditor / analizador-catalogo-test"
    "MELI_CLIENT_ID=$(ConvertTo-DotEnvValue $AuditorClientId)"
    "MELI_CLIENT_SECRET=$(ConvertTo-DotEnvValue $AuditorClientSecret)"
    "MELI_PUBLIC_KEY=$(ConvertTo-DotEnvValue $AuditorPublicKey)"
    "MELI_API_URL=$(ConvertTo-DotEnvValue $MeliApiUrl)"
)

[System.IO.File]::WriteAllLines($EnvPath, $Lines, (New-Object System.Text.UTF8Encoding($false)))
icacls $EnvPath /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null

Remove-Variable AxisClientId, AxisClientSecret, AuditorClientSecret, AuditorPublicKey, AuditorClientId -ErrorAction SilentlyContinue
Write-Host "Archivo creado con ACL restringida: $EnvPath"
```

Comprueba únicamente los nombres de las variables, nunca el contenido:

```powershell
Get-Content .env.mercadolibre | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=') { $matches[1] }
}
```

## Linux/macOS (Bash + `jq`)

Ejecutar dentro de una carpeta privada del MCP:

```bash
set -euo pipefail
PROJECT_ID="sylvan-cycle-487021-f7"
REGION="us-central1"
AUDITOR_SERVICE="analizador-catalogo-test"
ENV_PATH=".env.mercadolibre"

gcloud auth login
gcloud config set project "$PROJECT_ID"

AXIS_CLIENT_ID="$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret="axis-mercadolibre-client-id")"
AXIS_CLIENT_SECRET="$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret="axis-mercadolibre-client-secret")"
AUDITOR_CLIENT_SECRET="$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret="analizador-catalogo-test-meli-client-secret")"
AUDITOR_PUBLIC_KEY="$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret="analizador-catalogo-test-meli-public-key")"
AUDITOR_JSON="$(gcloud run services describe "$AUDITOR_SERVICE" --region="$REGION" --project="$PROJECT_ID" --format=json)"
AUDITOR_CLIENT_ID="$(printf '%s' "$AUDITOR_JSON" | jq -r '.spec.template.spec.containers[0].env[] | select(.name == "MELI_CLIENT_ID") | .value')"
MERCADOLIBRE_API_URL="$(printf '%s' "$AUDITOR_JSON" | jq -r '.spec.template.spec.containers[0].env[] | select(.name == "MERCADOLIBRE_API_URL") | .value')"
MERCADOLIBRE_SITE_ID="$(printf '%s' "$AUDITOR_JSON" | jq -r '.spec.template.spec.containers[0].env[] | select(.name == "MERCADOLIBRE_SITE_ID") | .value')"
MELI_API_URL="$(printf '%s' "$AUDITOR_JSON" | jq -r '.spec.template.spec.containers[0].env[] | select(.name == "MELI_API_URL") | .value')"

dotenv_quote() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | awk 'BEGIN{ORS="\\n"}{print}' | sed 's/\\n$//')"
}

umask 077
{
  printf '%s\n' '# Axis ML Data'
  printf 'MERCADOLIBRE_CLIENT_ID=%s\n' "$(dotenv_quote "$AXIS_CLIENT_ID")"
  printf 'MERCADOLIBRE_CLIENT_SECRET=%s\n' "$(dotenv_quote "$AXIS_CLIENT_SECRET")"
  printf 'MERCADOLIBRE_API_URL=%s\n' "$(dotenv_quote "$MERCADOLIBRE_API_URL")"
  printf 'MERCADOLIBRE_SITE_ID=%s\n' "$(dotenv_quote "$MERCADOLIBRE_SITE_ID")"
  printf '\n%s\n' '# Auditor / analizador-catalogo-test'
  printf 'MELI_CLIENT_ID=%s\n' "$(dotenv_quote "$AUDITOR_CLIENT_ID")"
  printf 'MELI_CLIENT_SECRET=%s\n' "$(dotenv_quote "$AUDITOR_CLIENT_SECRET")"
  printf 'MELI_PUBLIC_KEY=%s\n' "$(dotenv_quote "$AUDITOR_PUBLIC_KEY")"
  printf 'MELI_API_URL=%s\n' "$(dotenv_quote "$MELI_API_URL")"
} > "$ENV_PATH"

chmod 600 "$ENV_PATH"
unset AXIS_CLIENT_ID AXIS_CLIENT_SECRET AUDITOR_CLIENT_SECRET AUDITOR_PUBLIC_KEY AUDITOR_CLIENT_ID AUDITOR_JSON
printf 'Archivo creado con permisos 600: %s\n' "$ENV_PATH"
```

Verifica solo los nombres:

```bash
sed -n 's/^\([A-Z0-9_]*\)=.*/\1/p' .env.mercadolibre
```

## Conexión al MCP local

1. Copia `.env.mercadolibre` a la carpeta privada del MCP o configura su ruta de carga.
2. Confirma qué esquema acepta el MCP:
   - Si acepta `client_credentials`, usa `MERCADOLIBRE_CLIENT_ID` y `MERCADOLIBRE_CLIENT_SECRET`.
   - Si espera los aliases del Auditor, usa `MELI_CLIENT_ID`, `MELI_CLIENT_SECRET` y `MELI_PUBLIC_KEY`.
   - Si exige `authorization_code` y `refresh_token`, ejecuta la autorización OAuth del MCP; GCP no contiene ese refresh token para exportarlo.
3. No subas `.env.mercadolibre` a Git. Añádelo a `.gitignore` antes de iniciar el MCP.

```bash
printf '%s\n' '.env.mercadolibre' >> .gitignore
```

## Limpieza opcional

Cuando la migración haya terminado y el MCP ya use un almacén seguro, elimina el archivo local:

```powershell
Remove-Item -LiteralPath .env.mercadolibre
```

o:

```bash
rm -f -- .env.mercadolibre
```
