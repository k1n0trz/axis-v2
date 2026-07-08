from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal


@dataclass
class ChannelSaleRecord:
    business_unit_slug: str
    country_code: str
    channel_slug: str
    sale_date: date
    sales_amount: Decimal
    order_count: int = 0
    units: int = 0
    spend_amount: Decimal = Decimal("0")
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class CategorySaleRecord:
    business_unit_slug: str
    country_code: str
    channel_slug: str
    category_slug: str
    category_name: str
    sale_date: date
    sales_amount: Decimal
    original_amount: Decimal
    original_currency: str
    exchange_rate: Decimal
    quantity: int = 0
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class AdSpendRecord:
    business_unit_slug: str
    country_code: str
    ad_platform_slug: str
    spend_date: date
    spend_amount: Decimal
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class CategoryMetricRecord:
    business_unit_slug: str
    country_code: str
    category_slug: str
    category_name: str
    metric_date: date
    cpa_meta: Decimal | None = None
    cpa_google: Decimal | None = None
    spend_meta: Decimal = Decimal("0")
    spend_google: Decimal = Decimal("0")
    sales_amount: Decimal = Decimal("0")
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class FollowerMetricRecord:
    country_code: str
    metric_date: date
    instagram_profile_visits: int
    new_followers: int
    spend_amount: Decimal
    cpr: Decimal
    cps: Decimal
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ComfamaAdMetricRecord:
    metric_date: date
    category_slug: str
    category_name: str
    cpl: Decimal
    spend_amount: Decimal
    conversations: int
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class BaliMetricRecord:
    business_unit_slug: str
    country_code: str
    metric_date: date
    sessions: int
    web_sales_amount: Decimal
    web_order_count: int
    google_spend_amount: Decimal
    google_attributed_orders: int
    whatsapp_conversations: int
    cpa: Decimal
    source_file: str = ""
    notes: str = ""

    def to_dict(self):
        return asdict(self)
