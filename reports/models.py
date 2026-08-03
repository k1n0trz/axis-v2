from decimal import Decimal

from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import User


ZERO = Decimal('0')

class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class WeeklyReport(models.Model):
    week_label = models.CharField(max_length=120)
    date_start = models.DateField()
    date_end = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_start", "-created_at"]

    def __str__(self):
        return self.week_label


class Task(models.Model):
    AREA_ECOMMERCE = "Ecommerce"
    AREA_PAUTA = "Pauta"
    AREA_MARKETPLACE = "Marketplace"
    AREA_CHAT_WEB_BALI = "Chat Web Bali"
    AREA_CHOICES = [
        (AREA_ECOMMERCE, AREA_ECOMMERCE),
        (AREA_PAUTA, AREA_PAUTA),
        (AREA_MARKETPLACE, AREA_MARKETPLACE),
        (AREA_CHAT_WEB_BALI, AREA_CHAT_WEB_BALI),
    ]

    STATUS_COMPLETED = "Completado"
    STATUS_IN_PROGRESS = "En proceso"
    STATUS_PENDING = "Pendiente"
    STATUS_BLOCKED = "Bloqueado"
    STATUS_CHOICES = [
        (STATUS_COMPLETED, STATUS_COMPLETED),
        (STATUS_IN_PROGRESS, STATUS_IN_PROGRESS),
        (STATUS_PENDING, STATUS_PENDING),
        (STATUS_BLOCKED, STATUS_BLOCKED),
    ]

    PRIORITY_HIGH = "Alta"
    PRIORITY_MEDIUM = "Media"
    PRIORITY_LOW = "Baja"
    PRIORITY_CHOICES = [
        (PRIORITY_HIGH, PRIORITY_HIGH),
        (PRIORITY_MEDIUM, PRIORITY_MEDIUM),
        (PRIORITY_LOW, PRIORITY_LOW),
    ]

    report = models.ForeignKey(WeeklyReport, on_delete=models.CASCADE, related_name="tasks")
    area = models.CharField(max_length=30, choices=AREA_CHOICES)
    task_name = models.TextField()
    responsible = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES)
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["area", "-priority", "status", "id"]

    def __str__(self):
        return f"{self.area} - {self.task_name[:60]}"


class BusinessUnit(TimestampedModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    description = models.TextField(max_length=500, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Marca"
        verbose_name_plural = "Marcas"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class JobTitle(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(max_length=500, blank=True)
    is_leadership_role = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return self.name


class UserProfile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone_number = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    photo = models.FileField(upload_to="user_profiles/", blank=True)
    role = models.ForeignKey(JobTitle, null=True, blank=True, on_delete=models.SET_NULL, related_name="user_profiles")
    manager = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports")
    business_units = models.ManyToManyField(BusinessUnit, blank=True, related_name="user_profiles")

    class Meta:
        ordering = ["user__username"]
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"Perfil de {self.user.username}"


class Country(TimestampedModel):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=10, unique=True)
    business_units = models.ManyToManyField(BusinessUnit, blank=True, related_name="countries")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Pais"
        verbose_name_plural = "Paises"

    def __str__(self):
        return self.name


class Channel(TimestampedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    logo = models.FileField(upload_to="channel_logos/", blank=True)
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="channels", null=True, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subchannels")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Canal"
        verbose_name_plural = "Canales"
        unique_together = ("name", "business_unit")
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "slug"], condition=models.Q(business_unit__isnull=False), name="reports_channel_unit_slug_unique"),
            models.UniqueConstraint(fields=["slug"], condition=models.Q(business_unit__isnull=True), name="reports_channel_global_slug_unique"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductCategory(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(max_length=500)
    image = models.FileField(upload_to="product_categories/", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Categoria de producto"
        verbose_name_plural = "Categorias de producto"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DailyProductCategoryMetric(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="daily_product_category_metrics")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="daily_product_category_metrics")
    category = models.ForeignKey(ProductCategory, on_delete=models.CASCADE, related_name="daily_metrics")
    metric_date = models.DateField()
    cpa_meta = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cpa_google = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    spend_meta = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    spend_google = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_spend = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    sales_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.IMPORTED)
    source_file = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-metric_date", "category__name"]
        verbose_name = "Metrica diaria por categoria"
        verbose_name_plural = "Metricas diarias por categoria"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "category", "metric_date"], name="reports_daily_product_category_metric_unique"),
            models.CheckConstraint(condition=models.Q(cpa_meta__isnull=True) | models.Q(cpa_meta__gte=0), name="reports_category_metric_cpa_meta_nonnegative"),
            models.CheckConstraint(condition=models.Q(cpa_google__isnull=True) | models.Q(cpa_google__gte=0), name="reports_category_metric_cpa_google_nonnegative"),
            models.CheckConstraint(condition=models.Q(spend_meta__gte=0), name="reports_category_metric_spend_meta_nonnegative"),
            models.CheckConstraint(condition=models.Q(spend_google__gte=0), name="reports_category_metric_spend_google_nonnegative"),
            models.CheckConstraint(condition=models.Q(total_spend__gte=0), name="reports_category_metric_total_spend_nonnegative"),
            models.CheckConstraint(condition=models.Q(sales_amount__gte=0), name="reports_category_metric_sales_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["metric_date", "business_unit", "country", "category"], name="reports_dai_metric__c5542d_idx"),
        ]

    def __str__(self):
        return f"{self.category} - {self.metric_date}"

    def save(self, *args, **kwargs):
        self.total_spend = (self.spend_meta or ZERO) + (self.spend_google or ZERO)
        super().save(*args, **kwargs)


class DailyProductCategorySale(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="daily_product_category_sales")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="daily_product_category_sales")
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="daily_product_category_sales")
    category = models.ForeignKey(ProductCategory, on_delete=models.CASCADE, related_name="daily_channel_sales")
    sale_date = models.DateField()
    sales_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    original_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    original_currency = models.CharField(max_length=10, default="COP")
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    quantity = models.IntegerField(default=0)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.IMPORTED)
    source_file = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sale_date", "category__name", "channel__display_order"]
        verbose_name = "Venta diaria por categoria y canal"
        verbose_name_plural = "Ventas diarias por categoria y canal"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "channel", "category", "sale_date"], name="reports_daily_product_category_sale_unique"),
            models.CheckConstraint(condition=models.Q(exchange_rate__gte=0), name="reports_daily_product_category_sale_fx_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["sale_date", "business_unit", "country", "channel", "category"], name="reports_cat_sale_date_dims_idx"),
        ]

    def __str__(self):
        return f"{self.category} - {self.channel} - {self.sale_date}"

    def save(self, *args, **kwargs):
        if self.original_currency and self.original_currency.upper() != "COP" and self.original_amount and self.exchange_rate:
            self.sales_amount = self.original_amount * self.exchange_rate
        super().save(*args, **kwargs)


class ComfamaProductReference(TimestampedModel):
    category = models.ForeignKey(ProductCategory, on_delete=models.CASCADE, related_name="comfama_references")
    reference = models.CharField(max_length=120, unique=True)
    price_tariff_a = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    price_tariff_b = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_inferred = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["category__name", "reference"]
        verbose_name = "Referencia Comfama"
        verbose_name_plural = "Referencias Comfama"
        constraints = [
            models.CheckConstraint(condition=models.Q(price_tariff_a__gte=0), name="reports_comfama_ref_price_a_nonnegative"),
            models.CheckConstraint(condition=models.Q(price_tariff_b__gte=0), name="reports_comfama_ref_price_b_nonnegative"),
        ]

    def __str__(self):
        return self.reference


class ComfamaSale(TimestampedModel):
    class Tariff(models.TextChoices):
        TARIFF_A = "T-A", "Tarifa A"
        TARIFF_B = "T-B", "Tarifa B"

    sale_date = models.DateField()
    tariff = models.CharField(max_length=10, choices=Tariff.choices)
    reference = models.ForeignKey(ComfamaProductReference, on_delete=models.PROTECT, related_name="sales")
    sales_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    source_file = models.CharField(max_length=255, blank=True)
    source_row = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sale_date", "reference__category__name", "reference__reference"]
        verbose_name = "Venta Uva Comfama"
        verbose_name_plural = "Ventas Uva Comfama"
        constraints = [
            models.UniqueConstraint(fields=["source_file", "source_row"], condition=~models.Q(source_file=""), name="reports_comfama_sale_source_unique"),
            models.CheckConstraint(condition=models.Q(sales_amount__gte=0), name="reports_comfama_sale_amount_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["sale_date", "tariff"], name="rep_comf_sale_date_tariff_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.reference_id:
            if self.tariff == self.Tariff.TARIFF_A:
                self.sales_amount = self.reference.price_tariff_a
            elif self.tariff == self.Tariff.TARIFF_B:
                self.sales_amount = self.reference.price_tariff_b
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sale_date} - {self.reference} - {self.tariff}"


class ComfamaAdMetric(TimestampedModel):
    metric_date = models.DateField()
    category = models.ForeignKey(ProductCategory, on_delete=models.CASCADE, related_name="comfama_ad_metrics")
    cpl = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    spend_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    conversations = models.PositiveIntegerField(default=0)
    source_file = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-metric_date", "category__name"]
        verbose_name = "Pauta Uva Comfama"
        verbose_name_plural = "Pauta Uva Comfama"
        constraints = [
            models.UniqueConstraint(fields=["metric_date", "category"], name="reports_comfama_ad_metric_unique"),
            models.CheckConstraint(condition=models.Q(cpl__gte=0), name="reports_comfama_ad_cpl_nonnegative"),
            models.CheckConstraint(condition=models.Q(spend_amount__gte=0), name="reports_comfama_ad_spend_nonnegative"),
            models.CheckConstraint(condition=models.Q(conversations__gte=0), name="reports_comfama_ad_conversations_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["metric_date", "category"], name="rep_comf_ad_date_cat_idx"),
        ]

    def __str__(self):
        return f"{self.category} - {self.metric_date}"


class AwnInternationalFollowerMetric(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="awn_follower_metrics")
    metric_date = models.DateField(help_text="Fecha diaria de la campaña de seguidores en Instagram.")
    instagram_profile_visits = models.PositiveIntegerField(default=0, help_text="Visitas al perfil de Instagram registradas ese dia.")
    new_followers = models.PositiveIntegerField(default=0, help_text="Seguidores nuevos conseguidos ese dia.")
    spend_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Inversion diaria en COP.")
    cpr = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Costo por resultado o visita al perfil, en COP.")
    cps = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Costo por seguidor, en COP.")
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.IMPORTED)
    source_file = models.CharField(max_length=255, blank=True)
    source_row = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-metric_date", "country__name"]
        verbose_name = "Seguidores Awn Internacional"
        verbose_name_plural = "Seguidores Awn Internacional"
        constraints = [
            models.UniqueConstraint(fields=["country", "metric_date"], name="reports_awn_follower_metric_unique"),
            models.CheckConstraint(condition=models.Q(instagram_profile_visits__gte=0), name="reports_awn_visits_nonnegative"),
            models.CheckConstraint(condition=models.Q(new_followers__gte=0), name="reports_awn_followers_nonnegative"),
            models.CheckConstraint(condition=models.Q(spend_amount__gte=0), name="reports_awn_spend_nonnegative"),
            models.CheckConstraint(condition=models.Q(cpr__gte=0), name="reports_awn_cpr_nonnegative"),
            models.CheckConstraint(condition=models.Q(cps__gte=0), name="reports_awn_cps_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["metric_date", "country"], name="rep_awn_date_ctry_idx"),
        ]

    def __str__(self):
        return f"{self.country} - {self.metric_date}"


class Product(TimestampedModel):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, blank=True)
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="products", null=True, blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        unique_together = ("name", "business_unit")
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "slug"], condition=models.Q(business_unit__isnull=False), name="reports_product_unit_slug_unique"),
            models.UniqueConstraint(fields=["slug"], condition=models.Q(business_unit__isnull=True), name="reports_product_global_slug_unique"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MetricRecord(TimestampedModel):
    class PeriodType(models.TextChoices):
        WEEKLY = "weekly", "Semanal"
        MONTHLY = "monthly", "Mensual"

    class CampaignType(models.TextChoices):
        META_ADS = "Meta Ads", "Meta Ads"
        GOOGLE_ADS = "Google Ads", "Google Ads"
        TIKTOK_ADS = "TikTok Ads", "TikTok Ads"
        COMFAMA_UVA = "Comfama Uva", "Comfama Uva"
        RAPPI_ADS = "Rappi Ads", "Rappi Ads"
        FALABELLA_ADS = "Falabella Ads", "Falabella Ads"
        MERCADO_LIBRE_ADS = "Mercado Libre Ads", "Mercado Libre Ads"
        WHATSAPP_CAMPAIGNS = "WhatsApp Campaigns", "WhatsApp Campaigns"
        SELLERCHAT = "Sellerchat", "Sellerchat"

    class ValueOrigin(models.TextChoices):
        IMPORTED = "imported", "Importado"
        CALCULATED = "calculated", "Calculado"

    class MetricName(models.TextChoices):
        SALES_TOTAL = "sales_total", "Ventas totales"
        SALES_MONTH = "sales_month", "Ventas del mes"
        SALES_WHATSAPP = "sales_whatsapp", "Ventas por WhatsApp"
        SALES_WEB = "sales_web", "Ventas web"
        SALES_MARKETPLACE = "sales_marketplace", "Ventas marketplace"
        INVESTMENT = "investment", "Inversion"
        AD_SPEND = "ad_spend", "Gasto de pauta"
        AD_SPEND_BY_COUNTRY = "ad_spend_by_country", "Gasto de pauta por pais"
        INVESTMENT_BY_PRODUCT = "investment_by_product", "Inversion por producto"
        CPA = "cpa", "CPA"
        CPA_WEEKLY = "cpa_weekly", "CPA semanal"
        CPA_MONTHLY = "cpa_monthly", "CPA mensual"
        CPA_BY_PRODUCT = "cpa_by_product", "CPA por producto"
        CPL = "cpl", "CPL"
        CPL_WEEKLY = "cpl_weekly", "CPL semanal"
        CPL_MONTHLY = "cpl_monthly", "CPL mensual"
        CPL_BY_CAMPAIGN = "cpl_by_campaign", "CPL por campana"
        ROAS = "roas", "ROAS"
        MESSAGES = "messages", "Mensajes"
        CLICKS = "clicks", "Clicks"
        PURCHASES = "purchases", "Compras"
        CLOSED_DEALS = "closed_deals", "Negocios cerrados"
        CONVERSION_RATE = "conversion_rate", "Porcentaje de conversion"
        CLOSE_RATE = "close_rate", "Close rate"
        AVERAGE_TICKET = "average_ticket", "Ticket promedio"
        ORDERS = "orders", "Ordenes"
        UNITS = "units", "Unidades"
        UTILITY = "utility", "Utilidad"
        OPERATIONAL_PROFIT = "operational_profit", "Utilidad operativa"

    record_id = models.CharField(max_length=100, unique=True)
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="metric_records")
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="metric_records")
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True, related_name="metric_records")
    subchannel = models.CharField(max_length=120, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="metric_records")
    campaign_type = models.CharField(max_length=40, choices=CampaignType.choices, blank=True)
    source = models.CharField(max_length=120, blank=True)
    period_type = models.CharField(max_length=10, choices=PeriodType.choices)
    period_label = models.CharField(max_length=120)
    date_start = models.DateField()
    date_end = models.DateField()
    metric_name = models.CharField(max_length=40, choices=MetricName.choices)
    metric_value = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default="COP")
    value_origin = models.CharField(max_length=20, choices=ValueOrigin.choices, default=ValueOrigin.IMPORTED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_start", "business_unit__display_order", "channel__display_order", "metric_name"]
        indexes = [
            models.Index(fields=["period_type", "date_start", "date_end"]),
            models.Index(fields=["business_unit", "channel", "country"]),
            models.Index(fields=["metric_name", "period_label"]),
            models.Index(fields=["campaign_type", "value_origin"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(date_start__lte=models.F("date_end")), name="reports_metric_record_valid_date_range"),
            models.CheckConstraint(condition=models.Q(metric_value__gte=0), name="reports_metric_record_value_nonnegative"),
        ]

    def __str__(self):
        return f"{self.record_id} - {self.metric_name}"


class DailyChannelSale(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="daily_channel_sales")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="daily_channel_sales")
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="daily_channel_sales")
    sale_date = models.DateField()
    sales_amount = models.DecimalField(max_digits=18, decimal_places=2)
    order_count = models.PositiveIntegerField(default=0)
    units = models.PositiveIntegerField(default=0, blank=True)
    spend_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_file = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sale_date", "business_unit__display_order", "country__display_order"]
        verbose_name = "Venta diaria"
        verbose_name_plural = "Ventas diarias"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "channel", "sale_date"], name="reports_daily_channel_sale_unique"),
            models.CheckConstraint(condition=models.Q(sales_amount__gte=0), name="reports_daily_channel_sale_amount_nonnegative"),
            models.CheckConstraint(condition=models.Q(order_count__gte=0), name="reports_daily_channel_sale_orders_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["sale_date", "business_unit", "country", "channel"]),
        ]

    def __str__(self):
        return f"{self.business_unit} - {self.country} - {self.sale_date}"


class MarketplaceSale(DailyChannelSale):
    class Meta:
        proxy = True
        verbose_name = "Ventas Marketplace"
        verbose_name_plural = "Ventas Marketplace"


class MarketplaceProductInventory(TimestampedModel):
    class HealthStatus(models.TextChoices):
        OK = "ok", "Correcto"
        WARNING = "warning", "Advertencia"
        CRITICAL = "critical", "Critico"

    marketplace = models.CharField(max_length=40, default="mercadolibre")
    item_id = models.CharField(max_length=60, unique=True)
    title = models.CharField(max_length=255)
    sku = models.CharField(max_length=120, blank=True)
    gtin = models.CharField(max_length=80, blank=True)
    brand = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    category_id = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=40, blank=True)
    permalink = models.URLField(max_length=1000, blank=True)
    thumbnail_url = models.URLField(max_length=1000, blank=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    available_quantity = models.IntegerField(default=0)
    sold_quantity = models.IntegerField(default=0)
    health_status = models.CharField(max_length=20, choices=HealthStatus.choices, default=HealthStatus.OK)
    warning_messages = models.JSONField(default=list, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["health_status", "status", "title"]
        verbose_name = "Inventario Marketplace"
        verbose_name_plural = "Inventario Marketplace"
        indexes = [
            models.Index(fields=["marketplace", "status"]),
            models.Index(fields=["marketplace", "sku"]),
            models.Index(fields=["marketplace", "health_status"]),
            models.Index(fields=["-last_synced_at"]),
        ]

    def __str__(self):
        return f"{self.item_id} - {self.title}"


class SalesTarget(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sales_targets")
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="sales_targets")
    channel = models.ForeignKey(Channel, null=True, blank=True, on_delete=models.CASCADE, related_name="sales_targets")
    date_start = models.DateField()
    date_end = models.DateField()
    target_amount = models.DecimalField(max_digits=18, decimal_places=2)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date_start", "user__username", "channel__display_order"]
        verbose_name = "Meta de venta"
        verbose_name_plural = "Metas de venta"
        constraints = [
            models.CheckConstraint(condition=models.Q(date_start__lte=models.F("date_end")), name="reports_sales_target_valid_date_range"),
            models.CheckConstraint(condition=models.Q(target_amount__gte=0), name="reports_sales_target_amount_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["user", "business_unit", "channel", "date_start", "date_end"], name="reports_sales_target_dims_idx"),
        ]

    def __str__(self):
        channel_label = self.channel.name if self.channel_id else "Todos los canales"
        return f"{self.user} - {self.business_unit} - {channel_label}"


class RoasTrafficLightSetting(TimestampedModel):
    name = models.CharField(max_length=80, default="Semaforo ROAS", unique=True)
    green_min = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("4.00"), verbose_name="Verde desde")
    yellow_min = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("3.00"), verbose_name="Amarillo desde")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_active", "name"]
        verbose_name = "Semaforo ROAS"
        verbose_name_plural = "Semaforo ROAS"
        constraints = [
            models.CheckConstraint(condition=models.Q(green_min__gte=0), name="reports_roas_green_nonnegative"),
            models.CheckConstraint(condition=models.Q(yellow_min__gte=0), name="reports_roas_yellow_nonnegative"),
            models.CheckConstraint(condition=models.Q(yellow_min__lte=models.F("green_min")), name="reports_roas_threshold_order"),
        ]

    def __str__(self):
        return f"{self.name}: verde >= {self.green_min}, amarillo >= {self.yellow_min}"

    @classmethod
    def get_active(cls):
        setting = cls.objects.filter(is_active=True).order_by("-updated_at").first()
        if setting:
            return setting
        return cls.objects.create(name="Semaforo ROAS")

    def color_for(self, value):
        try:
            roas = Decimal(str(value or 0))
        except Exception:
            roas = ZERO
        if roas >= self.green_min:
            return "green"
        if roas >= self.yellow_min:
            return "yellow"
        return "red"


class OperationalGoalTask(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En proceso"
        COMPLETED = "completed", "Completada"

    sales_target = models.ForeignKey(SalesTarget, on_delete=models.CASCADE, related_name="operational_tasks", verbose_name="meta")
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assigned_operational_goal_tasks")
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="operational_goal_tasks")
    title = models.CharField(max_length=180, verbose_name="tarea")
    description = models.TextField(blank=True, verbose_name="instrucciones")
    goal_completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="% cumplimiento de meta",
        help_text="Porcentaje de cumplimiento que aporta o representa esta tarea operativa.",
    )
    due_date = models.DateField(null=True, blank=True, verbose_name="fecha limite")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="estado")
    employee_response = models.TextField(blank=True, verbose_name="comentarios o enlaces del empleado")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        verbose_name = "Meta operativa"
        verbose_name_plural = "Metas operativas"
        indexes = [
            models.Index(fields=["assigned_to", "status", "due_date"], name="reports_oper_task_user_idx"),
            models.Index(fields=["assigned_by", "status"], name="reports_oper_task_mgr_idx"),
        ]

    def __str__(self):
        return f"{self.title} - {self.assigned_to}"


class InsightAchievement(TimestampedModel):
    class AchievementType(models.TextChoices):
        SALES_TARGET = "sales_target", "Meta de ventas superada"
        SALES_GROWTH = "sales_growth", "Crecimiento de ventas"
        SPEND_EFFICIENCY = "spend_efficiency", "Reduccion eficiente de inversion"
        ROAS_GROWTH = "roas_growth", "Mejora de ROAS"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="insight_achievements")
    sales_target = models.ForeignKey(SalesTarget, on_delete=models.CASCADE, related_name="insight_achievements")
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="insight_achievements")
    channel = models.ForeignKey(Channel, null=True, blank=True, on_delete=models.SET_NULL, related_name="insight_achievements")
    month = models.DateField()
    achievement_type = models.CharField(max_length=32, choices=AchievementType.choices)
    title = models.CharField(max_length=180)
    description = models.TextField()
    metric_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    delta_percent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-month", "-metric_value", "-created_at"]
        verbose_name = "Logro automatico"
        verbose_name_plural = "Logros automaticos"
        constraints = [
            models.UniqueConstraint(
                fields=["sales_target", "month", "achievement_type"],
                name="reports_achievement_target_month_type_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "month"], name="rep_ach_user_month_idx"),
        ]

    def __str__(self):
        return f"{self.user} - {self.title} - {self.month:%Y-%m}"


class OperationalGoalTaskAttachment(TimestampedModel):
    task = models.ForeignKey(OperationalGoalTask, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="operational_task_attachments")
    file = models.FileField(upload_to="operational_tasks/%Y/%m/")
    label = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Adjunto de meta operativa"
        verbose_name_plural = "Adjuntos de metas operativas"

    def __str__(self):
        return self.label or self.file.name


class UserTask(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En proceso"
        COMPLETED = "completed", "Realizada"
        CANCELED = "canceled", "Cancelada"

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_user_tasks", verbose_name="creada por")
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="assigned_user_tasks", verbose_name="asignada a")
    title = models.CharField(max_length=180, verbose_name="titulo")
    description = models.TextField(blank=True, verbose_name="descripcion")
    links = models.TextField(blank=True, verbose_name="enlaces", help_text="Un enlace por linea.")
    due_date = models.DateField(null=True, blank=True, verbose_name="fecha de cumplimiento")
    due_time = models.TimeField(null=True, blank=True, verbose_name="hora de cumplimiento")
    registered_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="horas registradas")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="estado")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"
        indexes = [
            models.Index(fields=["assigned_to", "status", "due_date"], name="reports_user_task_user_idx"),
            models.Index(fields=["created_by", "status", "due_date"], name="reports_user_task_owner_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(registered_hours__gte=0), name="reports_user_task_hours_nonnegative"),
        ]

    def __str__(self):
        return f"{self.title} - {self.assigned_to or self.created_by}"


class UserTaskAttachment(TimestampedModel):
    task = models.ForeignKey(UserTask, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_task_attachments", verbose_name="subido por")
    file = models.FileField(upload_to="user_tasks/%Y/%m/", verbose_name="archivo")
    label = models.CharField(max_length=160, blank=True, verbose_name="etiqueta")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Adjunto de tarea"
        verbose_name_plural = "Adjuntos de tareas"

    def __str__(self):
        return self.label or self.file.name


class UserTaskLink(TimestampedModel):
    task = models.ForeignKey(UserTask, on_delete=models.CASCADE, related_name="task_links")
    url = models.URLField(max_length=500, verbose_name="enlace")
    label = models.CharField(max_length=160, blank=True, verbose_name="etiqueta")

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Enlace de tarea"
        verbose_name_plural = "Enlaces de tareas"

    def __str__(self):
        return self.label or self.url


class AdPlatform(TimestampedModel):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    description = models.TextField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Fuente de pauta"
        verbose_name_plural = "Fuentes de pauta"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DailyAdSpend(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="daily_ad_spends")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="daily_ad_spends")
    ad_platform = models.ForeignKey(AdPlatform, on_delete=models.CASCADE, related_name="daily_spends")
    spend_date = models.DateField()
    spend_amount = models.DecimalField(max_digits=18, decimal_places=2)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_file = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-spend_date", "business_unit__display_order", "country__display_order", "ad_platform__name"]
        verbose_name = "Inversion diaria"
        verbose_name_plural = "Inversiones diarias"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "ad_platform", "spend_date"], name="reports_daily_ad_spend_unique"),
            models.CheckConstraint(condition=models.Q(spend_amount__gte=0), name="reports_daily_ad_spend_amount_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["spend_date", "business_unit", "country", "ad_platform"]),
        ]

    def __str__(self):
        return f"{self.business_unit} - {self.country} - {self.ad_platform} - {self.spend_date}"


class DailyGeoAdMetric(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    class GeoLevel(models.TextChoices):
        COUNTRY = "country", "Pais"
        REGION = "region", "Region"
        CITY = "city", "Ciudad"

    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="daily_geo_ad_metrics")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="daily_geo_ad_metrics")
    ad_platform = models.ForeignKey(AdPlatform, on_delete=models.CASCADE, related_name="daily_geo_metrics")
    metric_date = models.DateField()
    geo_level = models.CharField(max_length=20, choices=GeoLevel.choices, default=GeoLevel.REGION)
    location_key = models.SlugField(max_length=140)
    location_name = models.CharField(max_length=160)
    platform_location_id = models.CharField(max_length=120, blank=True)
    impressions = models.PositiveBigIntegerField(default=0)
    reach = models.PositiveBigIntegerField(default=0)
    clicks = models.PositiveBigIntegerField(default=0)
    purchases = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO)
    conversion_value = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO)
    spend_amount = models.DecimalField(max_digits=18, decimal_places=2, default=ZERO)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.IMPORTED)
    source_file = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-metric_date", "business_unit__display_order", "country__display_order", "ad_platform__name", "geo_level", "location_name"]
        verbose_name = "Metrica geografica de pauta"
        verbose_name_plural = "Metricas geograficas de pauta"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "ad_platform", "metric_date", "geo_level", "location_key"], name="reports_geo_metric_unique"),
        ]
        indexes = [
            models.Index(fields=["metric_date", "business_unit", "country", "ad_platform"], name="reports_geo_date_dims_idx"),
            models.Index(fields=["country", "geo_level", "location_key"], name="reports_geo_location_idx"),
        ]

    def __str__(self):
        return f"{self.business_unit} - {self.country} - {self.ad_platform} - {self.location_name} - {self.metric_date}"


class Website(TimestampedModel):
    class Platform(models.TextChoices):
        WORDPRESS = "wordpress", "WordPress"
        SHOPIFY = "shopify", "Shopify"
        CUSTOM = "custom", "Custom"
        UNKNOWN = "unknown", "Desconocido"

    class Stage(models.TextChoices):
        ACTIVE = "active", "Activa"
        PENDING = "pending", "Pendiente"
        PAUSED = "paused", "Pausada"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    country_label = models.CharField(max_length=80, blank=True)
    url = models.URLField(max_length=500, blank=True)
    platform = models.CharField(max_length=24, choices=Platform.choices, default=Platform.UNKNOWN)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.ACTIVE)
    logo = models.FileField(upload_to="website_logos/", blank=True)
    business_unit = models.ForeignKey(BusinessUnit, null=True, blank=True, on_delete=models.SET_NULL, related_name="websites")
    monitor_enabled = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["display_order", "name", "country_label"]
        verbose_name = "Web"
        verbose_name_plural = "Webs"
        indexes = [
            models.Index(fields=["stage", "monitor_enabled"], name="reports_website_stage_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = " ".join(value for value in [self.name, self.country_label] if value)
            self.slug = slugify(base or self.url or self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        suffix = f" - {self.country_label}" if self.country_label else ""
        return f"{self.name}{suffix}"


class WebsiteHealthCheck(TimestampedModel):
    class OverallStatus(models.TextChoices):
        HEALTHY = "healthy", "Saludable"
        WARNING = "warning", "Alerta"
        CRITICAL = "critical", "Critica"
        UNKNOWN = "unknown", "Sin dato"

    class AvailabilityStatus(models.TextChoices):
        ONLINE = "online", "Online"
        REDIRECT = "redirect", "Redireccion"
        OFFLINE = "offline", "Offline"
        ERROR = "error", "Error"
        UNKNOWN = "unknown", "Sin dato"

    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="health_checks")
    checked_at = models.DateTimeField()
    overall_status = models.CharField(max_length=20, choices=OverallStatus.choices, default=OverallStatus.UNKNOWN)
    availability_status = models.CharField(max_length=20, choices=AvailabilityStatus.choices, default=AvailabilityStatus.UNKNOWN)
    http_status = models.PositiveIntegerField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    final_url = models.URLField(max_length=1000, blank=True)
    page_title = models.CharField(max_length=255, blank=True)
    platform_detected = models.CharField(max_length=40, blank=True)
    is_https = models.BooleanField(default=False)
    ssl_valid = models.BooleanField(null=True, blank=True)
    ssl_expires_at = models.DateTimeField(null=True, blank=True)
    ssl_days_remaining = models.IntegerField(null=True, blank=True)
    security_headers_score = models.PositiveSmallIntegerField(default=0)
    security_headers_total = models.PositiveSmallIntegerField(default=0)
    missing_security_headers = models.JSONField(default=list, blank=True)
    pagespeed_status = models.CharField(max_length=24, default="unknown")
    performance_score = models.PositiveSmallIntegerField(null=True, blank=True)
    accessibility_score = models.PositiveSmallIntegerField(null=True, blank=True)
    best_practices_score = models.PositiveSmallIntegerField(null=True, blank=True)
    seo_score = models.PositiveSmallIntegerField(null=True, blank=True)
    first_contentful_paint_ms = models.PositiveIntegerField(null=True, blank=True)
    largest_contentful_paint_ms = models.PositiveIntegerField(null=True, blank=True)
    speed_index_ms = models.PositiveIntegerField(null=True, blank=True)
    total_blocking_time_ms = models.PositiveIntegerField(null=True, blank=True)
    cumulative_layout_shift = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    products_visible_status = models.CharField(max_length=24, default="unknown")
    products_visible_count = models.PositiveIntegerField(null=True, blank=True)
    products_in_stock_count = models.PositiveIntegerField(null=True, blank=True)
    products_out_of_stock_count = models.PositiveIntegerField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-checked_at", "website__display_order"]
        verbose_name = "Chequeo de web"
        verbose_name_plural = "Chequeos de webs"
        indexes = [
            models.Index(fields=["website", "-checked_at"], name="reports_webcheck_latest_idx"),
            models.Index(fields=["overall_status", "checked_at"], name="reports_webcheck_status_idx"),
        ]

    def __str__(self):
        return f"{self.website} - {self.checked_at:%Y-%m-%d %H:%M}"


class BaliDailyMetric(TimestampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Importado"

    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="bali_daily_metrics")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="bali_daily_metrics")
    metric_date = models.DateField()
    sessions = models.PositiveIntegerField(default=0)
    web_sales_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    web_order_count = models.PositiveIntegerField(default=0)
    google_spend_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    google_attributed_orders = models.PositiveIntegerField(default=0)
    whatsapp_conversations = models.PositiveIntegerField(default=0)
    cpa = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_file = models.CharField(max_length=255, blank=True)
    source_row = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-metric_date"]
        verbose_name = "Metrica diaria Bali"
        verbose_name_plural = "Metricas diarias Bali"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "metric_date"], name="reports_bali_daily_metric_unique"),
            models.CheckConstraint(condition=models.Q(sessions__gte=0), name="reports_bali_daily_sessions_nonnegative"),
            models.CheckConstraint(condition=models.Q(web_order_count__gte=0), name="reports_bali_daily_orders_nonnegative"),
            models.CheckConstraint(condition=models.Q(google_spend_amount__gte=0), name="reports_bali_daily_spend_nonnegative"),
            models.CheckConstraint(condition=models.Q(google_attributed_orders__gte=0), name="reports_bali_daily_google_orders_nonnegative"),
            models.CheckConstraint(condition=models.Q(whatsapp_conversations__gte=0), name="reports_bali_daily_conversations_nonnegative"),
            models.CheckConstraint(condition=models.Q(cpa__gte=0), name="reports_bali_daily_cpa_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["metric_date", "business_unit", "country"], name="reports_bali_metric_d_bc_idx"),
        ]

    def __str__(self):
        return f"Bali - {self.metric_date}"


class BaliWebProductDailyMetric(TimestampedModel):
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="bali_web_product_daily_metrics")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="bali_web_product_daily_metrics")
    metric_date = models.DateField()
    product_title = models.CharField(max_length=255)
    net_items_sold = models.IntegerField(default=0)
    gross_sales = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    discounts = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    returns = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    net_sales = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_sales = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    product_image_url = models.URLField(max_length=1000, blank=True, default="")
    source_file = models.CharField(max_length=255, blank=True, default="shopifyql")

    class Meta:
        ordering = ["-metric_date", "product_title"]
        verbose_name = "Producto web diario Bali"
        verbose_name_plural = "Productos web diarios Bali"
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "country", "metric_date", "product_title"],
                name="reports_bali_web_product_daily_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["metric_date", "business_unit", "country"], name="reports_bali_prod_d_bc_idx"),
        ]

    def __str__(self):
        return f"Bali Web - {self.product_title} - {self.metric_date}"


class BaliCommunityWebcamMetric(TimestampedModel):
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="bali_community_webcam_metrics")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="bali_community_webcam_metrics")
    metric_date = models.DateField()
    new_subscribers = models.PositiveIntegerField(default=0)
    subscribers = models.PositiveIntegerField(default=0)
    story_screenshot = models.FileField(upload_to="bali_community_webcam/%Y/%m/", blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-metric_date"]
        verbose_name = "Comunidad Webcam Bali"
        verbose_name_plural = "Comunidad Webcam Bali"
        constraints = [
            models.UniqueConstraint(fields=["business_unit", "country", "metric_date"], name="reports_bali_community_unique"),
            models.CheckConstraint(condition=models.Q(new_subscribers__gte=0), name="reports_bali_community_new_nonnegative"),
            models.CheckConstraint(condition=models.Q(subscribers__gte=0), name="reports_bali_community_total_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["metric_date", "business_unit", "country"], name="reports_bali_comm_d_bc_idx"),
        ]

    def __str__(self):
        return f"Comunidad Webcam Bali - {self.metric_date}"


class BaliWhatsAppSale(DailyChannelSale):
    class Meta:
        proxy = True
        verbose_name = "WhatsApp Bali"
        verbose_name_plural = "WhatsApp Bali"


class BaliPhysicalStoreSale(DailyChannelSale):
    class Meta:
        proxy = True
        verbose_name = "Tienda Fisica Bali"
        verbose_name_plural = "Tienda Fisica Bali"


class AgendaTask(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En proceso"
        COMPLETED = "completed", "Completada"
        CANCELED = "canceled", "Cancelada"

    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agenda_created_tasks")
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agenda_assigned_tasks")
    due_at = models.DateTimeField(verbose_name="fecha de finalizacion")
    reminder_at = models.DateTimeField(null=True, blank=True, verbose_name="fecha de recordatorio")
    reminder_enabled = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["status", "due_at", "-created_at"]
        verbose_name = "Agenda"
        verbose_name_plural = "Agenda"
        indexes = [
            models.Index(fields=["assigned_to", "status", "due_at"]),
            models.Index(fields=["reminder_enabled", "reminder_at"]),
        ]

    def __str__(self):
        return self.title


class WeeklyTask(TimestampedModel):
    class Area(models.TextChoices):
        ECOMMERCE = "Ecommerce", "Ecommerce"
        PAUTA = "Pauta", "Pauta"
        MARKETPLACE = "Marketplace", "Marketplace"
        CHAT_WEB_BALI = "Chat Web Bali", "Chat - Web Bali"
        TECNICO = "Tecnico", "Tecnico"
        OPERATIVO = "Operativo", "Operativo"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En proceso"
        COMPLETED = "completed", "Completada"
        BLOCKED = "blocked", "Bloqueada"

    class Priority(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Critica"

    class TaskType(models.TextChoices):
        OPERATIVA = "operativa", "Operativa"
        ESTRATEGICA = "estrategica", "Estrategica"
        CORRECTIVA = "correctiva", "Correctiva"
        PREVENTIVA = "preventiva", "Preventiva"
        INCIDENCIA = "incidencia", "Incidencia"
        OPTIMIZACION = "optimizacion", "Optimizacion"

    class Impact(models.TextChoices):
        VENTAS = "ventas", "Ventas"
        CONVERSION = "conversion", "Conversion"
        OPERACION = "operacion", "Operacion"
        TECNOLOGIA = "tecnologia", "Tecnologia"
        RENTABILIDAD = "rentabilidad", "Rentabilidad"
        EXPERIENCIA_CLIENTE = "experiencia_cliente", "Experiencia cliente"
        RIESGO = "riesgo", "Riesgo"

    task_id = models.CharField(max_length=100, unique=True)
    week_label = models.CharField(max_length=120)
    date_start = models.DateField()
    date_end = models.DateField()
    area = models.CharField(max_length=20, choices=Area.choices)
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="weekly_tasks")
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="weekly_tasks")
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True, related_name="weekly_tasks")
    task_name = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices)
    priority = models.CharField(max_length=20, choices=Priority.choices)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)
    impact = models.CharField(max_length=30, choices=Impact.choices)
    result = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    related_metric = models.ForeignKey(MetricRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="related_tasks")
    attachment_ref = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-date_start", "-priority", "status", "area", "task_id"]
        indexes = [
            models.Index(fields=["date_start", "date_end"]),
            models.Index(fields=["business_unit", "channel", "country"]),
            models.Index(fields=["status", "priority", "impact"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(date_start__lte=models.F("date_end")), name="reports_weekly_task_valid_date_range"),
        ]

    def __str__(self):
        return f"{self.week_label} - {self.task_name[:60]}"


class Attachment(TimestampedModel):
    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        PRESENTATION = "presentation", "Presentacion"
        IMAGE = "image", "Imagen"
        EXCEL = "excel", "Excel"
        DOCUMENT = "document", "Documento"

    attachment_ref = models.CharField(max_length=120, unique=True)
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments")
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments")
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments")
    period_label = models.CharField(max_length=120, blank=True)
    task = models.ForeignKey(WeeklyTask, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FileType.choices)
    uploaded_file = models.FileField(upload_to="attachments/%Y/%m/", blank=True)
    file_path_or_url = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "file_name"]

    def __str__(self):
        return self.file_name

    @property
    def file_link(self):
        if self.uploaded_file:
            return self.uploaded_file.url
        return self.file_path_or_url


class SalesTransaction(TimestampedModel):
    business_unit = models.ForeignKey(BusinessUnit, on_delete=models.CASCADE, related_name="sales_transactions")
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_transactions")
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_transactions")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_transactions")
    product_name = models.CharField(max_length=255)
    origin = models.CharField(max_length=120, blank=True)
    sale_date = models.DateField()
    quantity = models.PositiveIntegerField(default=0)
    sale_value = models.DecimalField(max_digits=18, decimal_places=2)
    shipping_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    source_file = models.CharField(max_length=255, blank=True)
    source_sheet = models.CharField(max_length=80, blank=True)
    source_row = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sale_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["source_file", "source_sheet", "source_row"], name="reports_sale_source_row_unique"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="reports_sale_quantity_nonnegative"),
            models.CheckConstraint(condition=models.Q(sale_value__gte=0), name="reports_sale_value_nonnegative"),
            models.CheckConstraint(condition=models.Q(shipping_value__gte=0), name="reports_sale_shipping_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["sale_date", "country", "channel"]),
            models.Index(fields=["business_unit", "sale_date"]),
        ]

    def __str__(self):
        return f"{self.product_name} - {self.sale_date}"


class ImportJob(TimestampedModel):
    class Status(models.TextChoices):
        PREVIEW = "preview", "Preview"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREVIEW)
    summary = models.TextField(blank=True)
    critical_errors = models.PositiveIntegerField(default=0)
    warnings = models.PositiveIntegerField(default=0)
    preview_payload = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.file_name}"


class ExportJob(TimestampedModel):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    file_name = models.CharField(max_length=255)
    export_scope = models.CharField(max_length=80, default="master")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    filters = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Export {self.file_name}"




class IntegrationRun(TimestampedModel):
    """Bitacora de ejecuciones de integraciones.

    Estaba en el roadmap de automatizacion desde mayo y nunca se construyo. Sin
    ella, cuando un dato no aparece en el tablero no hay forma de saber si el job
    no corrio, corrio y fallo, o corrio bien y la fuente venia vacia. Las tres
    cosas se ven igual: una celda sin numero.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        SUCCESS = "success", "Exito"
        FAILED = "failed", "Fallo"
        SKIPPED = "skipped", "Omitida"

    source = models.CharField(max_length=80, help_text="Fuente o job: woocommerce_co, google_ads_distrisex, websites_health...")
    command = models.CharField(max_length=120, blank=True, help_text="Comando de management que la ejecuto.")
    target_date = models.DateField(null=True, blank=True, help_text="Fecha de negocio procesada, no la de ejecucion.")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Ejecucion de integracion"
        verbose_name_plural = "Ejecuciones de integraciones"
        indexes = [
            models.Index(fields=["source", "-started_at"], name="reports_integrationrun_src_idx"),
            models.Index(fields=["status", "-started_at"], name="reports_integrationrun_st_idx"),
        ]

    def __str__(self):
        fecha = self.target_date.isoformat() if self.target_date else "sin fecha"
        return f"{self.source} {fecha} ({self.get_status_display()})"

    @property
    def duration_seconds(self):
        if not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class AiConversation(TimestampedModel):
    """Una conversacion con la IA interna, por usuario y por sesion."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_conversations")
    session_key = models.CharField(max_length=64, blank=True, help_text="Sesion del navegador que la inicio.")
    title = models.CharField(max_length=160, blank=True)
    summary = models.TextField(
        blank=True,
        help_text="Resumen de los turnos viejos. Se manda en vez de la historia completa.",
    )
    summarized_until = models.PositiveIntegerField(
        default=0, help_text="Id del ultimo mensaje que ya entro en el resumen."
    )
    distilled_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Conversacion IA"
        verbose_name_plural = "Conversaciones IA"
        indexes = [models.Index(fields=["user", "-updated_at"], name="reports_aiconv_user_idx")]

    def __str__(self):
        return f"{self.user.username}: {self.title or 'sin titulo'}"


class AiMessage(TimestampedModel):
    """Un mensaje de la conversacion, con lo que costo.

    El costo se guarda por mensaje y no se recalcula: los precios cambian, y un
    historico recalculado con el precio de hoy no serviria para auditar el gasto.
    """

    class Role(models.TextChoices):
        SYSTEM = "system", "Sistema"
        USER = "user", "Usuario"
        ASSISTANT = "assistant", "IA"
        TOOL = "tool", "Herramienta"

    conversation = models.ForeignKey(AiConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True)
    model = models.CharField(max_length=80, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal("0"))
    tools_used = models.JSONField(default=list, blank=True)

    class Feedback(models.TextChoices):
        NONE = "", "Sin calificar"
        UP = "up", "Sirvio"
        DOWN = "down", "No sirvio"

    feedback = models.CharField(max_length=8, choices=Feedback.choices, blank=True, default="")

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Mensaje IA"
        verbose_name_plural = "Mensajes IA"
        indexes = [models.Index(fields=["conversation", "created_at"], name="reports_aimsg_conv_idx")]

    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:60]}"

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens


class AiAttachment(TimestampedModel):
    """Un archivo que alguien le paso a la IA, disponible en las siguientes sesiones.

    Se guarda por usuario y no por conversacion: el usuario sube el Excel de despachos
    una vez y lo sigue teniendo la semana siguiente. `conversation` solo deja constancia
    de donde salio.

    El `sha256` es la clave real: subir dos veces el mismo archivo no crea dos filas ni
    dos objetos en el bucket. Sin eso, un archivo que alguien reenvia cada dia se
    acumula sin que nadie lo note.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_attachments")
    conversation = models.ForeignKey(
        AiConversation, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments"
    )
    file = models.FileField(upload_to="ai_attachments/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Archivo IA"
        verbose_name_plural = "Archivos IA"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "sha256"], name="reports_aiattachment_user_hash_unique"
            )
        ]
        indexes = [models.Index(fields=["user", "is_active"], name="reports_aiatt_user_idx")]

    def __str__(self):
        return f"{self.user.username}: {self.original_name}"


class AiMemory(TimestampedModel):
    """Lo que la IA aprendio de una persona y le sirve en la siguiente conversacion.

    Se guarda como texto legible a proposito: el usuario tiene que poder leer y borrar
    lo que la IA cree saber de el. Una memoria equivocada que no se puede ver es peor
    que no tener memoria.

    El contenido sale de mensajes del usuario, asi que para el modelo es DATO: se
    inyecta en un bloque marcado como notas, nunca como instrucciones del sistema.
    """

    class Kind(models.TextChoices):
        PREFERENCE = "preference", "Preferencia de trabajo"
        STYLE = "style", "Forma de comunicarse"
        CONTEXT = "context", "Contexto de la operacion"
        DECISION = "decision", "Decision tomada"

    class Origin(models.TextChoices):
        DISTILLED = "distilled", "Deducida de una conversacion"
        EXPLICIT = "explicit", "El usuario pidio recordarla"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_memories")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.CONTEXT)
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.DISTILLED)
    content = models.TextField()
    source_conversation = models.ForeignKey(
        AiConversation, null=True, blank=True, on_delete=models.SET_NULL, related_name="memories"
    )
    is_active = models.BooleanField(default=True)
    times_used = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_used_at", "-updated_at"]
        verbose_name = "Memoria IA"
        verbose_name_plural = "Memorias IA"
        indexes = [models.Index(fields=["user", "is_active"], name="reports_aimem_user_idx")]

    def __str__(self):
        return f"{self.user.username}: {self.content[:60]}"
