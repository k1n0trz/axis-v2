from pathlib import Path
from urllib.parse import parse_qs, urlparse

from decouple import Csv, config

# Compatibilidad con configuracion antigua y nueva por pais.
#
# Importante: las variables legacy WC_* pertenecen a integraciones antiguas y
# no deben usarse como fallback para WooCommerce Uva por pais. Si CO/MX no esta
# configurado de forma explicita, los jobs diarios deben omitir esa fuente para
# evitar importar ventas de otra tienda dentro de Uva.
WOOCOMMERCE_CONSUMER_KEY = config(
    "WOOCOMMERCE_CONSUMER_KEY",
    default=config("WC_CLIENT_KEY", default=""),
)
WOOCOMMERCE_CONSUMER_SECRET = config(
    "WOOCOMMERCE_CONSUMER_SECRET",
    default=config("WC_SECRET_KEY", default=""),
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="unsafe-dev-key")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "reports.apps.ReportsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "reports.security.AdminSessionRequiredMiddleware",
    "reports.query_cache.QueryMemoMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


DB_CONN_MAX_AGE = config("DB_CONN_MAX_AGE", default=60, cast=int)


def database_from_url(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    host = query.get("host", [parsed.hostname or ""])[0]
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": host,
        "PORT": parsed.port or "",
        # Sin esto Django abre y cierra una conexion por request, lo que en
        # Cloud Run suma el handshake de Cloud SQL a cada carga de pagina.
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
        "CONN_HEALTH_CHECKS": True,
    }


DATABASE_URL = config("DATABASE_URL", default="")
DATABASES = {
    "default": database_from_url(DATABASE_URL)
    if DATABASE_URL
    else {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_MEDIA = config("SERVE_MEDIA", default=True, cast=bool)
GS_BUCKET_NAME = config("GS_BUCKET_NAME", default="")
GS_MEDIA_LOCATION = config("GS_MEDIA_LOCATION", default="")
STORAGES = {
    "default": {
        "BACKEND": "reports.storage_backends.AxisGoogleCloudMediaStorage"
        if GS_BUCKET_NAME
        else "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

ONEDRIVE_CLIENT_ID = config("ONEDRIVE_CLIENT_ID", default="")
ONEDRIVE_CLIENT_SECRET = config("ONEDRIVE_CLIENT_SECRET", default="")
ONEDRIVE_TENANT_ID = config("ONEDRIVE_TENANT_ID", default="common")
ONEDRIVE_REDIRECT_URI = config("ONEDRIVE_REDIRECT_URI", default="")
ONEDRIVE_AUTH_MODE = config("ONEDRIVE_AUTH_MODE", default="delegated")
ONEDRIVE_ACCESS_TOKEN = config("ONEDRIVE_ACCESS_TOKEN", default="")
ONEDRIVE_REFRESH_TOKEN = config("ONEDRIVE_REFRESH_TOKEN", default="")
ONEDRIVE_TOKEN_EXPIRES_AT = config("ONEDRIVE_TOKEN_EXPIRES_AT", default="")
ONEDRIVE_USER_ID = config("ONEDRIVE_USER_ID", default="")
ONEDRIVE_SHARED_SALES_FILE_PATH = config("ONEDRIVE_SHARED_SALES_FILE_PATH", default="")
ONEDRIVE_SHARED_COMFAMA_FILE_PATH = config("ONEDRIVE_SHARED_COMFAMA_FILE_PATH", default="")
ONEDRIVE_GOOGLE_ADS_FILE_PATH = config("ONEDRIVE_GOOGLE_ADS_FILE_PATH", default="")
ONEDRIVE_AWARENESS_FILE_PATH = config("ONEDRIVE_AWARENESS_FILE_PATH", default="")
ONEDRIVE_WHATSAPP_FILE_PATH = config("ONEDRIVE_WHATSAPP_FILE_PATH", default="")
ONEDRIVE_ECUADOR_FILE_PATH = config("ONEDRIVE_ECUADOR_FILE_PATH", default="")
ONEDRIVE_COLOMBIA_SHEET = config("ONEDRIVE_COLOMBIA_SHEET", default="Colombia")
ONEDRIVE_ECUADOR_SHEET = config("ONEDRIVE_ECUADOR_SHEET", default="Ecuador")
ONEDRIVE_SALES_LOOKBACK_DAYS = config("ONEDRIVE_SALES_LOOKBACK_DAYS", default=3, cast=int)

WOOCOMMERCE_CO_BASE_URL = config("WOOCOMMERCE_CO_BASE_URL", default="")
WOOCOMMERCE_CO_CONSUMER_KEY = config("WOOCOMMERCE_CO_CONSUMER_KEY", default="")
WOOCOMMERCE_CO_CONSUMER_SECRET = config("WOOCOMMERCE_CO_CONSUMER_SECRET", default="")
WOOCOMMERCE_MX_BASE_URL = config("WOOCOMMERCE_MX_BASE_URL", default="")
WOOCOMMERCE_MX_CONSUMER_KEY = config("WOOCOMMERCE_MX_CONSUMER_KEY", default="")
WOOCOMMERCE_MX_CONSUMER_SECRET = config("WOOCOMMERCE_MX_CONSUMER_SECRET", default="")

# DistriSex es la tienda mayorista (catalogo Bali + Uva). Vende en Colombia, pero
# con tienda y credenciales propias, asi que se identifica por tienda y no por
# pais: fetch_woocommerce_sales --store DISTRISEX --country CO. Los legacy WC_*
# apuntan a esta misma tienda y se aceptan como respaldo.
WOOCOMMERCE_DISTRISEX_BASE_URL = config(
    "WOOCOMMERCE_DISTRISEX_BASE_URL",
    default=config("WC_STORE_URL", default=""),
)
WOOCOMMERCE_DISTRISEX_CONSUMER_KEY = config(
    "WOOCOMMERCE_DISTRISEX_CONSUMER_KEY",
    default=config("WC_CLIENT_KEY", default=""),
)
WOOCOMMERCE_DISTRISEX_CONSUMER_SECRET = config(
    "WOOCOMMERCE_DISTRISEX_CONSUMER_SECRET",
    default=config("WC_SECRET_KEY", default=""),
)

META_ACCESS_TOKEN = config("META_ACCESS_TOKEN", default="")
META_API_VERSION = config("META_API_VERSION", default="v20.0")
META_CO_ACCOUNT_ID = config("META_CO_ACCOUNT_ID", default="")
META_MX_ACCOUNT_ID = config("META_MX_ACCOUNT_ID", default="")
META_EC_ACCOUNT_ID = config("META_EC_ACCOUNT_ID", default="")

GOOGLE_ADS_DEVELOPER_TOKEN = config("GOOGLE_ADS_DEVELOPER_TOKEN", default="")
GOOGLE_ADS_CLIENT_ID = config("GOOGLE_ADS_CLIENT_ID", default="")
GOOGLE_ADS_CLIENT_SECRET = config("GOOGLE_ADS_CLIENT_SECRET", default="")
GOOGLE_ADS_ACCESS_TOKEN = config("GOOGLE_ADS_ACCESS_TOKEN", default="")
GOOGLE_ADS_REFRESH_TOKEN = config("GOOGLE_ADS_REFRESH_TOKEN", default="")
GOOGLE_ADS_TOKEN_EXPIRES_AT = config("GOOGLE_ADS_TOKEN_EXPIRES_AT", default="")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = config("GOOGLE_ADS_LOGIN_CUSTOMER_ID", default="")
GOOGLE_ADS_CO_CUSTOMER_ID = config("GOOGLE_ADS_CO_CUSTOMER_ID", default="")
GOOGLE_ADS_MX_CUSTOMER_ID = config("GOOGLE_ADS_MX_CUSTOMER_ID", default="")
GOOGLE_ADS_EC_CUSTOMER_ID = config("GOOGLE_ADS_EC_CUSTOMER_ID", default="")
GOOGLE_ADS_BALI_CUSTOMER_ID = config("GOOGLE_ADS_BALI_CUSTOMER_ID", default="")
GOOGLE_ADS_BALI_WHATSAPP_CONVERSION_NAME = config("GOOGLE_ADS_BALI_WHATSAPP_CONVERSION_NAME", default="Balisexstore - GA4 (web) boton_de_whatsapp")

SHOPIFY_BALI_SHOP_DOMAIN = config("SHOPIFY_BALI_SHOP_DOMAIN", default="")
SHOPIFY_BALI_ACCESS_TOKEN = config("SHOPIFY_BALI_ACCESS_TOKEN", default="")
SHOPIFY_BALI_API_VERSION = config("SHOPIFY_BALI_API_VERSION", default="2025-10")

MERCADOLIBRE_CLIENT_ID = config("MERCADOLIBRE_CLIENT_ID", default=config("MELI_CLIENT_ID", default=""))
MERCADOLIBRE_CLIENT_SECRET = config("MERCADOLIBRE_CLIENT_SECRET", default=config("MELI_CLIENT_SECRET", default=""))
MERCADOLIBRE_ACCESS_TOKEN = config("MERCADOLIBRE_ACCESS_TOKEN", default=config("MELI_ACCESS_TOKEN", default=""))
MERCADOLIBRE_API_URL = config("MERCADOLIBRE_API_URL", default=config("MELI_API_URL", default="https://api.mercadolibre.com"))
MERCADOLIBRE_SITE_ID = config("MERCADOLIBRE_SITE_ID", default=config("MELI_SITE_ID", default="MCO"))
MERCADOLIBRE_SELLER_ID = config("MERCADOLIBRE_SELLER_ID", default=config("MELI_SELLER_ID", default=""))
MARKETPLACE_API_TIME_ZONE = config("MARKETPLACE_API_TIME_ZONE", default="America/Bogota")
FALABELLA_API_URL = config("FALABELLA_API_URL", default="https://sellercenter-api.falabella.com")
FALABELLA_USER_ID = config("FALABELLA_USER_ID", default="")
FALABELLA_API_KEY = config("FALABELLA_API_KEY", default="")

EXCHANGE_RATE_API_URL = config("EXCHANGE_RATE_API_URL", default="https://api.exchangerate.host")
EXCHANGE_RATE_API_KEY = config("EXCHANGE_RATE_API_KEY", default="")
PAGESPEED_API_KEY = config("PAGESPEED_API_KEY", default="")
PAGESPEED_TIMEOUT = config("PAGESPEED_TIMEOUT", default=90, cast=int)

AXIS_SYNC_RUN_REGION = config("AXIS_SYNC_RUN_REGION", default="us-central1")
AXIS_SYNC_RUN_JOB_NAME = config("AXIS_SYNC_RUN_JOB_NAME", default="axis-temp-sync-daily")

META_REPORTS_IMAP_HOST = config("META_REPORTS_IMAP_HOST", default="")
META_REPORTS_IMAP_PORT = config("META_REPORTS_IMAP_PORT", default=993, cast=int)
META_REPORTS_IMAP_USERNAME = config("META_REPORTS_IMAP_USERNAME", default="")
META_REPORTS_IMAP_PASSWORD = config("META_REPORTS_IMAP_PASSWORD", default="")
META_REPORTS_IMAP_FOLDER = config("META_REPORTS_IMAP_FOLDER", default="INBOX")
META_REPORTS_IMAP_SUBJECT_FILTER = config("META_REPORTS_IMAP_SUBJECT_FILTER", default="Meta Ads")
META_REPORTS_IMAP_FROM_FILTER = config("META_REPORTS_IMAP_FROM_FILTER", default="")
META_REPORTS_DOWNLOAD_DIR = config("META_REPORTS_DOWNLOAD_DIR", default=str(BASE_DIR / "data" / "meta-reports"))

# Caché compartida entre workers e instancias. El backend por defecto de Django
# es local al proceso, asi que con gunicorn --workers 2 cada worker mantenia su
# propia copia y el TTL de las vistas caras (Meta Ads) casi nunca se aprovechaba.
CACHE_TABLE_NAME = "axis_cache"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": CACHE_TABLE_NAME,
        "TIMEOUT": 300,
        "OPTIONS": {"MAX_ENTRIES": 5000, "CULL_FREQUENCY": 4},
    },
    # Para lecturas muy repetidas dentro de un mismo render (filtros de
    # plantilla). Ir a la cache compartida aqui solo cambiaria una consulta por
    # otra; esta vive en memoria del proceso y no toca la base de datos.
    "local": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "axis-local",
        "TIMEOUT": 60,
    },
}

META_ADS_PREVIEW_TIMEOUT = config("META_ADS_PREVIEW_TIMEOUT", default=8, cast=int)
# La llamada a Meta tarda ~12 s, asi que la cache se precalienta en segundo
# plano (comando warm_meta_ads_preview) y el TTL debe cubrir con holgura el
# intervalo entre precalentamientos.
META_ADS_PREVIEW_CACHE_SECONDS = config("META_ADS_PREVIEW_CACHE_SECONDS", default=14400, cast=int)
# Los resultados vacios o con error tambien se cachean, con un TTL corto, para
# que un fallo de Meta no obligue a repetir el camino lento en cada request.
META_ADS_PREVIEW_FALLBACK_CACHE_SECONDS = config("META_ADS_PREVIEW_FALLBACK_CACHE_SECONDS", default=120, cast=int)
# Timeout del endpoint que completa el panel (api/uva/meta-ads-panel/). Es
# holgado porque esa llamada ya no esta en el camino de la pagina: el usuario ve
# el tablero completo mientras el panel se resuelve aparte. Medido: ~15 s reales.
META_ADS_PREVIEW_PANEL_TIMEOUT = config("META_ADS_PREVIEW_PANEL_TIMEOUT", default=60, cast=int)

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "axis": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "axis",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Sin esto los fallos de integracion se perdian en silencio.
        "reports": {
            "handlers": ["console"],
            "level": config("AXIS_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}

