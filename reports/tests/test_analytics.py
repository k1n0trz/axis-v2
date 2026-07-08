from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from reports.models import MetricRecord
from reports.services.analytics import aggregate_metrics, roas_by_unit


def _record(metric_name, value, unit_name, *, channel_name="General"):
    return SimpleNamespace(
        metric_name=metric_name,
        metric_value=Decimal(value),
        business_unit=SimpleNamespace(name=unit_name),
        channel=SimpleNamespace(name=channel_name),
        value_origin=MetricRecord.ValueOrigin.IMPORTED,
    )


class AnalyticsSummaryTests(SimpleTestCase):
    def test_aggregate_metrics_counts_all_sales_channels_in_sales_total(self):
        records = [
            _record(MetricRecord.MetricName.SALES_MONTH, "100", "Uva"),
            _record(MetricRecord.MetricName.SALES_WEB, "200", "Bali"),
            _record(MetricRecord.MetricName.SALES_MARKETPLACE, "300", "Marketplace"),
        ]

        kpis = aggregate_metrics(records)

        self.assertEqual(kpis["sales_total"], 600.0)

    def test_roas_by_unit_uses_monthly_sales_and_fallback_spend_metrics(self):
        records = [
            _record(MetricRecord.MetricName.SALES_MONTH, "900", "Uva"),
            _record(MetricRecord.MetricName.INVESTMENT_BY_PRODUCT, "300", "Uva"),
            _record(MetricRecord.MetricName.SALES_MARKETPLACE, "400", "Marketplace"),
            _record(MetricRecord.MetricName.AD_SPEND_BY_COUNTRY, "200", "Marketplace"),
        ]

        rows = roas_by_unit(records)

        self.assertEqual(rows, [{"label": "Uva", "value": 3.0}, {"label": "Marketplace", "value": 2.0}])
