from collections import Counter, defaultdict
from decimal import Decimal

from reports.models import Attachment, MetricRecord, WeeklyTask

ZERO = Decimal("0")
PREFER_IMPORTED_DERIVED_METRICS = True
MESSAGE_ALIASES = {"messages", "chats", "conversations"}
SALES_TOTAL_ALIASES = {"sales", "sales_total", "ventas"}
SALES_METRIC_NAMES = SALES_TOTAL_ALIASES | {
    MetricRecord.MetricName.SALES_MONTH,
    MetricRecord.MetricName.SALES_WEB,
    MetricRecord.MetricName.SALES_WHATSAPP,
    MetricRecord.MetricName.SALES_MARKETPLACE,
}
SPEND_DIRECT_METRIC_NAMES = {MetricRecord.MetricName.AD_SPEND}
SPEND_FALLBACK_METRIC_NAMES = {
    MetricRecord.MetricName.AD_SPEND_BY_COUNTRY,
    MetricRecord.MetricName.INVESTMENT,
    MetricRecord.MetricName.INVESTMENT_BY_PRODUCT,
}


def build_filter_dict(params):
    return {
        "period_type": params.get("period_type") or "monthly",
        "date_start": params.get("date_start") or "",
        "date_end": params.get("date_end") or "",
        "time_granularity": params.get("time_granularity") or "daily",
        "compare_mode": params.get("compare_mode") or "previous_period",
        "business_unit": params.get("business_unit") or "",
        "country": params.get("country") or "",
        "channel": params.get("channel") or "",
        "area": params.get("area") or "",
        "week_label": params.get("week_label") or "",
        "product": params.get("product") or "",
        "campaign_type": params.get("campaign_type") or "",
    }


def apply_metric_filters(queryset, filters):
    if filters.get("period_type") and filters["period_type"] != "custom":
        queryset = queryset.filter(period_type=filters["period_type"])
    if filters.get("date_start"):
        queryset = queryset.filter(date_start__gte=filters["date_start"])
    if filters.get("date_end"):
        queryset = queryset.filter(date_end__lte=filters["date_end"])
    if filters.get("business_unit"):
        queryset = queryset.filter(business_unit__slug=filters["business_unit"])
    if filters.get("country"):
        queryset = queryset.filter(country__code=filters["country"])
    if filters.get("channel"):
        queryset = queryset.filter(channel__slug=filters["channel"])
    if filters.get("product"):
        queryset = queryset.filter(product__slug=filters["product"])
    if filters.get("campaign_type"):
        queryset = queryset.filter(campaign_type=filters["campaign_type"])
    return queryset


def apply_task_filters(queryset, filters):
    if filters.get("date_start"):
        queryset = queryset.filter(date_start__gte=filters["date_start"])
    if filters.get("date_end"):
        queryset = queryset.filter(date_end__lte=filters["date_end"])
    if filters.get("business_unit"):
        queryset = queryset.filter(business_unit__slug=filters["business_unit"])
    if filters.get("country"):
        queryset = queryset.filter(country__code=filters["country"])
    if filters.get("channel"):
        queryset = queryset.filter(channel__slug=filters["channel"])
    if filters.get("area"):
        queryset = queryset.filter(area=filters["area"])
    if filters.get("week_label"):
        queryset = queryset.filter(week_label__icontains=filters["week_label"])
    return queryset


def apply_attachment_filters(queryset, filters):
    if filters.get("business_unit"):
        queryset = queryset.filter(business_unit__slug=filters["business_unit"])
    if filters.get("country"):
        queryset = queryset.filter(country__code=filters["country"])
    if filters.get("channel"):
        queryset = queryset.filter(channel__slug=filters["channel"])
    if filters.get("area"):
        queryset = queryset.filter(task__area=filters["area"])
    if filters.get("week_label"):
        queryset = queryset.filter(task__week_label__icontains=filters["week_label"])
    return queryset


def metric_records(filters):
    queryset = MetricRecord.objects.select_related("business_unit", "country", "channel", "product")
    return list(apply_metric_filters(queryset, filters))


def weekly_tasks(filters):
    queryset = WeeklyTask.objects.select_related("business_unit", "country", "channel", "related_metric")
    return list(apply_task_filters(queryset, filters))


def attachments(filters):
    queryset = Attachment.objects.select_related("business_unit", "country", "channel", "task")
    return list(apply_attachment_filters(queryset, filters))


def _total_by_metric_names(records, metric_names):
    return sum((record.metric_value for record in records if record.metric_name in metric_names), ZERO)


def _average_by_metric_names(records, metric_names):
    values = [record.metric_value for record in records if record.metric_name in metric_names]
    return (sum(values, ZERO) / Decimal(len(values))) if values else ZERO


def _first_imported(records, metric_name):
    imported_values = [record.metric_value for record in records if record.metric_name == metric_name and record.value_origin == MetricRecord.ValueOrigin.IMPORTED]
    return imported_values[0] if imported_values else ZERO


def aggregate_metrics(records):
    sales_total = _total_by_metric_names(records, SALES_METRIC_NAMES)
    sales_month = _total_by_metric_names(records, {MetricRecord.MetricName.SALES_MONTH})
    sales_whatsapp = _total_by_metric_names(records, {MetricRecord.MetricName.SALES_WHATSAPP})
    sales_web = _total_by_metric_names(records, {MetricRecord.MetricName.SALES_WEB})
    sales_marketplace = _total_by_metric_names(records, {MetricRecord.MetricName.SALES_MARKETPLACE})
    investment = _total_by_metric_names(records, {MetricRecord.MetricName.INVESTMENT})
    ad_spend_direct = _total_by_metric_names(records, SPEND_DIRECT_METRIC_NAMES)
    ad_spend_by_country = _total_by_metric_names(records, {MetricRecord.MetricName.AD_SPEND_BY_COUNTRY})
    ad_spend_fallback = _total_by_metric_names(records, SPEND_FALLBACK_METRIC_NAMES)
    ad_spend = ad_spend_direct or ad_spend_fallback
    investment_by_product = _total_by_metric_names(records, {MetricRecord.MetricName.INVESTMENT_BY_PRODUCT})
    purchases = _total_by_metric_names(records, {MetricRecord.MetricName.PURCHASES})
    messages = _total_by_metric_names(records, MESSAGE_ALIASES)
    closed_deals = _total_by_metric_names(records, {MetricRecord.MetricName.CLOSED_DEALS})
    orders = _total_by_metric_names(records, {MetricRecord.MetricName.ORDERS})
    units = _total_by_metric_names(records, {MetricRecord.MetricName.UNITS})
    utility = _total_by_metric_names(records, {MetricRecord.MetricName.UTILITY})
    operational_profit = _total_by_metric_names(records, {MetricRecord.MetricName.OPERATIONAL_PROFIT})
    average_ticket = _average_by_metric_names(records, {MetricRecord.MetricName.AVERAGE_TICKET})
    cpa_average = _average_by_metric_names(records, {MetricRecord.MetricName.CPA, MetricRecord.MetricName.CPA_WEEKLY, MetricRecord.MetricName.CPA_MONTHLY, MetricRecord.MetricName.CPA_BY_PRODUCT})
    cpl_average = _average_by_metric_names(records, {MetricRecord.MetricName.CPL, MetricRecord.MetricName.CPL_WEEKLY, MetricRecord.MetricName.CPL_MONTHLY, MetricRecord.MetricName.CPL_BY_CAMPAIGN})

    base_investment = ad_spend or investment
    imported_roas = _first_imported(records, MetricRecord.MetricName.ROAS)
    imported_conversion = _first_imported(records, MetricRecord.MetricName.CONVERSION_RATE)
    imported_close_rate = _first_imported(records, MetricRecord.MetricName.CLOSE_RATE)

    calculated_roas = (sales_total / base_investment) if base_investment else ZERO
    calculated_conversion = (purchases / messages) if messages else ZERO
    calculated_close_rate = (closed_deals / messages) if messages else ZERO

    roas = imported_roas if (PREFER_IMPORTED_DERIVED_METRICS and imported_roas) else calculated_roas
    conversion_rate = imported_conversion if (PREFER_IMPORTED_DERIVED_METRICS and imported_conversion) else calculated_conversion
    close_rate = imported_close_rate if (PREFER_IMPORTED_DERIVED_METRICS and imported_close_rate) else calculated_close_rate

    return {
        "sales_total": float(sales_total),
        "sales_month": float(sales_month),
        "sales_whatsapp": float(sales_whatsapp),
        "sales_web": float(sales_web),
        "sales_marketplace": float(sales_marketplace),
        "investment": float(investment),
        "ad_spend": float(ad_spend),
        "investment_by_product": float(investment_by_product),
        "roas": round(float(roas), 2) if roas else 0,
        "messages": float(messages),
        "purchases": float(purchases),
        "conversion_rate": round(float(conversion_rate), 4) if conversion_rate else 0,
        "closed_deals": float(closed_deals),
        "close_rate": round(float(close_rate), 4) if close_rate else 0,
        "orders": float(orders),
        "units": float(units),
        "utility": float(utility),
        "operational_profit": float(operational_profit),
        "average_ticket": float(average_ticket),
        "cpa_average": round(float(cpa_average), 2) if cpa_average else 0,
        "cpl_average": round(float(cpl_average), 2) if cpl_average else 0,
        "cpa_weekly": float(_total_by_metric_names(records, {MetricRecord.MetricName.CPA_WEEKLY, MetricRecord.MetricName.CPA_BY_PRODUCT})),
        "cpa_monthly": float(_total_by_metric_names(records, {MetricRecord.MetricName.CPA_MONTHLY})),
        "cpl_weekly": float(_total_by_metric_names(records, {MetricRecord.MetricName.CPL_WEEKLY, MetricRecord.MetricName.CPL_BY_CAMPAIGN})),
        "cpl_monthly": float(_total_by_metric_names(records, {MetricRecord.MetricName.CPL_MONTHLY})),
        "ad_spend_by_country": float(ad_spend_by_country),
    }


def group_metric_records(records, key_func, label_func, metric_names=None):
    metric_names = set(metric_names or {MetricRecord.MetricName.SALES_TOTAL})
    grouped = defaultdict(lambda: ZERO)
    for record in records:
        if record.metric_name in metric_names:
            grouped[key_func(record)] += record.metric_value
    return [{"label": label_func(key), "value": float(value)} for key, value in sorted(grouped.items(), key=lambda item: item[1], reverse=True)]


def roas_by_unit(records):
    buckets = defaultdict(lambda: {"sales_total": ZERO, "ad_spend": ZERO, "fallback_spend": ZERO})
    for record in records:
        key = record.business_unit.name
        if record.metric_name in SALES_METRIC_NAMES:
            buckets[key]["sales_total"] += record.metric_value
        elif record.metric_name in SPEND_DIRECT_METRIC_NAMES:
            buckets[key]["ad_spend"] += record.metric_value
        elif record.metric_name in SPEND_FALLBACK_METRIC_NAMES:
            buckets[key]["fallback_spend"] += record.metric_value
    data = []
    for key, values in buckets.items():
        base = values["ad_spend"] or values["fallback_spend"]
        roas = values["sales_total"] / base if base else ZERO
        data.append({"label": key, "value": round(float(roas), 2) if roas else 0})
    return sorted(data, key=lambda item: item["value"], reverse=True)


def build_insights(kpis, sales_unit_rows, roas_rows, task_rows):
    def cop(value):
        formatted = f"{float(value or 0):,.0f}".replace(",", ".")
        return f"${formatted} COP"

    insights = []
    alerts = []
    if sales_unit_rows:
        top = sales_unit_rows[0]
        insights.append(f"{top['label']} lidera ventas con {cop(top['value'])}.")
    if roas_rows:
        top_roas = roas_rows[0]
        insights.append(f"{top_roas['label']} muestra el mejor ROAS con {top_roas['value']:.2f}.")
    if kpis["sales_whatsapp"]:
        insights.append(f"WhatsApp aporta {cop(kpis['sales_whatsapp'])} en ventas para el filtro actual.")
    blocked = sum(1 for task in task_rows if task.status == WeeklyTask.Status.BLOCKED)
    critical = sum(1 for task in task_rows if task.priority == WeeklyTask.Priority.CRITICAL)
    if blocked:
        alerts.append(f"Hay {blocked} tareas bloqueadas que requieren seguimiento gerencial.")
    if critical:
        alerts.append(f"Se registran {critical} tareas criticas esta semana.")
    if kpis["ad_spend"] and kpis["roas"] < 3:
        alerts.append("El ROAS consolidado esta por debajo del umbral de referencia 3.0.")
    if not insights:
        insights.append("No hay suficientes datos para generar insights automaticos todavia.")
    return insights[:4], alerts[:4]


def build_dashboard_summary(filters):
    records = metric_records(filters)
    tasks = weekly_tasks(filters)
    kpis = aggregate_metrics(records)
    kpis["weekly_tasks"] = len(tasks)
    kpis["critical_tasks"] = sum(1 for task in tasks if task.priority == WeeklyTask.Priority.CRITICAL)
    kpis["blocked_tasks"] = sum(1 for task in tasks if task.status == WeeklyTask.Status.BLOCKED)

    sales_metrics = SALES_METRIC_NAMES
    sales_by_unit = group_metric_records(records, lambda record: record.business_unit.name, lambda value: value, sales_metrics)
    sales_by_channel = group_metric_records(records, lambda record: record.channel.name if record.channel else "Sin canal", lambda value: value, sales_metrics)
    roas_rows = roas_by_unit(records)
    insights, alerts = build_insights(kpis, sales_by_unit, roas_rows, tasks)

    operation_summary = {
        "by_area": dict(Counter(task.area for task in tasks)),
        "by_status": dict(Counter(task.get_status_display() for task in tasks)),
        "by_impact": dict(Counter(task.impact for task in tasks)),
    }

    return {
        "filters": filters,
        "kpis": kpis,
        "insights": insights,
        "alerts": alerts,
        "sales_by_unit": sales_by_unit,
        "sales_by_channel": sales_by_channel,
        "roas_by_unit": roas_rows,
        "operation_summary": operation_summary,
    }


def build_unit_summary(unit_slug, filters):
    unit_filters = dict(filters)
    unit_filters["business_unit"] = unit_slug
    records = metric_records(unit_filters)
    tasks = weekly_tasks(unit_filters)
    summary = build_dashboard_summary(unit_filters)
    summary["records"] = records
    summary["tasks"] = tasks
    sales_metrics = SALES_TOTAL_ALIASES | {MetricRecord.MetricName.SALES_WHATSAPP, MetricRecord.MetricName.SALES_WEB, MetricRecord.MetricName.SALES_MARKETPLACE}
    summary["country_sales"] = group_metric_records(records, lambda record: record.country.name if record.country else "Sin pais", lambda value: value, sales_metrics)
    summary["product_sales"] = group_metric_records(records, lambda record: record.product.name if record.product else "Sin producto", lambda value: value, SALES_TOTAL_ALIASES | {MetricRecord.MetricName.SALES_MONTH})
    summary["investment_by_product_rows"] = group_metric_records(records, lambda record: record.product.name if record.product else "Sin producto", lambda value: value, {MetricRecord.MetricName.INVESTMENT_BY_PRODUCT})
    summary["ad_spend_by_country"] = group_metric_records(records, lambda record: record.country.name if record.country else "Sin pais", lambda value: value, {MetricRecord.MetricName.AD_SPEND_BY_COUNTRY})
    summary["ad_spend_by_channel"] = group_metric_records(records, lambda record: record.channel.name if record.channel else "Sin canal", lambda value: value, {MetricRecord.MetricName.AD_SPEND, MetricRecord.MetricName.AD_SPEND_BY_COUNTRY, MetricRecord.MetricName.INVESTMENT})
    summary["messages_by_channel"] = group_metric_records(records, lambda record: record.channel.name if record.channel else "Sin canal", lambda value: value, {MetricRecord.MetricName.MESSAGES})
    summary["cpa_by_product"] = group_metric_records(records, lambda record: record.product.name if record.product else "Sin producto", lambda value: value, {MetricRecord.MetricName.CPA, MetricRecord.MetricName.CPA_WEEKLY, MetricRecord.MetricName.CPA_MONTHLY, MetricRecord.MetricName.CPA_BY_PRODUCT})
    summary["cpl_whatsapp"] = group_metric_records(records, lambda record: record.period_label, lambda value: value, {MetricRecord.MetricName.CPL, MetricRecord.MetricName.CPL_WEEKLY, MetricRecord.MetricName.CPL_MONTHLY, MetricRecord.MetricName.CPL_BY_CAMPAIGN})
    comfama_records = [record for record in records if record.campaign_type == MetricRecord.CampaignType.COMFAMA_UVA]
    summary["comfama_sales_by_product"] = group_metric_records(comfama_records, lambda record: record.product.name if record.product else "Sin producto", lambda value: value, SALES_TOTAL_ALIASES | {MetricRecord.MetricName.SALES_MONTH})
    summary["comfama_messages_by_product"] = group_metric_records(comfama_records, lambda record: record.product.name if record.product else "Sin producto", lambda value: value, {MetricRecord.MetricName.MESSAGES})
    summary["comfama_investment_by_product"] = group_metric_records(comfama_records, lambda record: record.product.name if record.product else "Sin producto", lambda value: value, {MetricRecord.MetricName.INVESTMENT})
    return summary


