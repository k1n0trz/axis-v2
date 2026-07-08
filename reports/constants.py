"""Constantes centralizadas para Axis."""
from django.conf import settings


class Constants:
    DEFAULT_COUNTRY = "CO"
    DEFAULT_CURRENCY = "COP"

    COLOMBIA = "CO"
    ECUADOR = "EC"
    MEXICO = "MX"
    ESPANA = "ES"

    CURRENCIES = {
        "COP": {"code": "COP", "name": "Peso Colombiano", "symbol": "$", "decimal_places": 2},
        "USD": {"code": "USD", "name": "Dólar Americano", "symbol": "$", "decimal_places": 2},
        "MXN": {"code": "MXN", "name": "Peso Mexicano", "symbol": "$", "decimal_places": 2},
        "EUR": {"code": "EUR", "name": "Euro", "symbol": "€", "decimal_places": 2},
    }

    COUNTRY_NAMES = {
        "CO": "Colombia",
        "MX": "Mexico",
        "EC": "Ecuador",
        "ES": "Espana",
    }

    CURRENCY_ALIASES = {
        "CO": "COP",
        "COP": "COP",
        "USD": "USD",
        "MXN": "MXN",
        "EUR": "EUR",
    }

    @classmethod
    def get_currency_code(cls, currency: str) -> str:
        return cls.CURRENCY_ALIASES.get(currency.upper(), cls.DEFAULT_CURRENCY)

    @classmethod
    def get_country_name(cls, code: str) -> str:
        return cls.COUNTRY_NAMES.get(code, code)


class PeriodType:
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

    CHOICES = [
        (WEEKLY, "Semana"),
        (MONTHLY, "Mes"),
        (QUARTERLY, "Trimestre"),
        (YEARLY, "Año"),
        (CUSTOM, "Personalizado"),
    ]


class TaskStatus:
    COMPLETED = "Completado"
    IN_PROGRESS = "En proceso"
    PENDING = "Pendiente"
    BLOCKED = "Bloqueado"

    CHOICES = [
        (COMPLETED, COMPLETED),
        (IN_PROGRESS, IN_PROGRESS),
        (PENDING, PENDING),
        (BLOCKED, BLOCKED),
    ]

    ORDER = {
        COMPLETED: 0,
        IN_PROGRESS: 1,
        PENDING: 2,
        BLOCKED: 3,
    }


class TaskPriority:
    HIGH = "Alta"
    MEDIUM = "Media"
    LOW = "Baja"
    CRITICAL = "Critical"

    CHOICES = [
        (CRITICAL, CRITICAL),
        (HIGH, HIGH),
        (MEDIUM, MEDIUM),
        (LOW, LOW),
    ]

    ORDER = {
        CRITICAL: 0,
        HIGH: 1,
        MEDIUM: 2,
        LOW: 3,
    }


class BusinessUnitSlug:
    UVA = "uva"
    BALI = "bali"
    MARKETPLACE = "marketplace"


class ChannelSlug:
    ECOMMERCE_UVA = "ecommerce-uva"
    WHATSAPP_UVA_CO = "whatsapp-uva-co"
    COMFAMA_UVA = "comfama-uva"
    MERCADO_LIBRE = "mercado-libre"
    FALABELLA = "falabella"
    FARMATODO = "farmatodo"


class MetricName:
    SALES_TOTAL = "sales_total"
    SALES_MONTH = "sales_month"
    SALES_WHATSAPP = "sales_whatsapp"
    SALES_WEB = "sales_web"
    SALES_MARKETPLACE = "sales_marketplace"
    INVESTMENT = "investment"
    AD_SPEND = "ad_spend"
    AD_SPEND_BY_COUNTRY = "ad_spend_by_country"
    INVESTMENT_BY_PRODUCT = "investment_by_product"
    CPA = "cpa"
    CPA_WEEKLY = "cpa_weekly"
    CPA_MONTHLY = "cpa_monthly"
    CPA_BY_PRODUCT = "cpa_by_product"
    CPL = "cpl"
    CPL_WEEKLY = "cpl_weekly"
    CPL_MONTHLY = "cpl_monthly"
    CPL_BY_CAMPAIGN = "cpl_by_campaign"
    ROAS = "roas"
    MESSAGES = "messages"
    PURCHASES = "purchases"
    CONVERSION_RATE = "conversion_rate"
    CLOSE_RATE = "close_rate"
    ORDERS = "orders"
    UNITS = "units"
    AVERAGE_TICKET = "average_ticket"
    UTILITY = "utility"
    OPERATIONAL_PROFIT = "operational_profit"


CONFIG = {
    "DEBUG": settings.DEBUG,
    "DEFAULT_COUNTRY": Constants.DEFAULT_COUNTRY,
    "DEFAULT_CURRENCY": Constants.DEFAULT_CURRENCY,
}