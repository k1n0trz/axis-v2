"""Settings para correr la suite.

Sin esto los tests salen a internet: `.env` tiene credenciales reales, asi que un
test que renderiza /uva/ hacia una llamada de verdad a Meta Ads (~18 s), y
cualquier test nuevo que toque una integracion haria lo mismo sin que nadie lo
note. Aqui se vacian todas las credenciales externas: el codigo ya trata la
ausencia de credenciales como "esta fuente no esta configurada" y devuelve un
resultado vacio, que es justo lo que una prueba necesita.

Un test que quiera ejercitar una integracion debe declararlo con
`override_settings` y un mock, no heredarlo del entorno de quien corre la suite.

`manage.py test` usa este modulo por defecto.
"""
from .base import *  # noqa: F403

DEBUG = False

# Credenciales externas: todas vacias.
META_ACCESS_TOKEN = ""
META_CO_ACCOUNT_ID = ""
META_MX_ACCOUNT_ID = ""
META_EC_ACCOUNT_ID = ""

GOOGLE_ADS_DEVELOPER_TOKEN = ""
GOOGLE_ADS_CLIENT_ID = ""
GOOGLE_ADS_CLIENT_SECRET = ""
GOOGLE_ADS_ACCESS_TOKEN = ""
GOOGLE_ADS_REFRESH_TOKEN = ""
GOOGLE_ADS_LOGIN_CUSTOMER_ID = ""
GOOGLE_ADS_CO_CUSTOMER_ID = ""
GOOGLE_ADS_MX_CUSTOMER_ID = ""
GOOGLE_ADS_EC_CUSTOMER_ID = ""
GOOGLE_ADS_BALI_CUSTOMER_ID = ""

ONEDRIVE_CLIENT_ID = ""
ONEDRIVE_CLIENT_SECRET = ""
ONEDRIVE_ACCESS_TOKEN = ""
ONEDRIVE_REFRESH_TOKEN = ""

WOOCOMMERCE_CO_BASE_URL = ""
WOOCOMMERCE_CO_CONSUMER_KEY = ""
WOOCOMMERCE_CO_CONSUMER_SECRET = ""
WOOCOMMERCE_MX_BASE_URL = ""
WOOCOMMERCE_MX_CONSUMER_KEY = ""
WOOCOMMERCE_MX_CONSUMER_SECRET = ""
WOOCOMMERCE_DISTRISEX_BASE_URL = ""
WOOCOMMERCE_DISTRISEX_CONSUMER_KEY = ""
WOOCOMMERCE_DISTRISEX_CONSUMER_SECRET = ""

SHOPIFY_BALI_SHOP_DOMAIN = ""
SHOPIFY_BALI_ACCESS_TOKEN = ""

MERCADOLIBRE_ACCESS_TOKEN = ""
MERCADOLIBRE_CLIENT_ID = ""
MERCADOLIBRE_CLIENT_SECRET = ""
FALABELLA_USER_ID = ""
FALABELLA_API_KEY = ""

EXCHANGE_RATE_API_KEY = ""
PAGESPEED_API_KEY = ""

DEEPSEEK_API_KEY = ""
DEEPINFRA_API_KEY = ""

META_REPORTS_IMAP_HOST = ""
META_REPORTS_IMAP_USERNAME = ""
META_REPORTS_IMAP_PASSWORD = ""

# Hashear contrasenas con el algoritmo real solo hace lentas las pruebas.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
