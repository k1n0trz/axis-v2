from rest_framework import serializers

from .models import Attachment, BusinessUnit, Channel, Country, DailyProductCategoryMetric, MetricRecord, Product, ProductCategory, WeeklyTask
from .services.analytics import build_dashboard_summary


class BusinessUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessUnit
        fields = ("id", "name", "slug")


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ("id", "name", "code")


class ChannelSerializer(serializers.ModelSerializer):
    business_unit = BusinessUnitSerializer(read_only=True)

    class Meta:
        model = Channel
        fields = ("id", "name", "slug", "business_unit")


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ("id", "name", "slug", "description", "image")


class DailyProductCategoryMetricSerializer(serializers.ModelSerializer):
    category = ProductCategorySerializer(read_only=True)
    country = CountrySerializer(read_only=True)

    class Meta:
        model = DailyProductCategoryMetric
        fields = "__all__"


class ProductSerializer(serializers.ModelSerializer):
    category = ProductCategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = ("id", "name", "slug", "category")


class MetricRecordSerializer(serializers.ModelSerializer):
    business_unit = BusinessUnitSerializer(read_only=True)
    country = CountrySerializer(read_only=True)
    channel = ChannelSerializer(read_only=True)
    product = ProductSerializer(read_only=True)

    class Meta:
        model = MetricRecord
        fields = "__all__"


class WeeklyTaskSerializer(serializers.ModelSerializer):
    business_unit = BusinessUnitSerializer(read_only=True)
    country = CountrySerializer(read_only=True)
    channel = ChannelSerializer(read_only=True)

    class Meta:
        model = WeeklyTask
        fields = "__all__"


class AttachmentSerializer(serializers.ModelSerializer):
    business_unit = BusinessUnitSerializer(read_only=True)
    channel = ChannelSerializer(read_only=True)
    country = CountrySerializer(read_only=True)
    task = WeeklyTaskSerializer(read_only=True)
    file_link = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = "__all__"

    def get_file_link(self, obj):
        return obj.file_link


class DashboardSummarySerializer(serializers.Serializer):
    filters = serializers.DictField()
    kpis = serializers.DictField()
    insights = serializers.ListField(child=serializers.CharField())
    alerts = serializers.ListField(child=serializers.CharField())
    sales_by_unit = serializers.ListField()
    sales_by_channel = serializers.ListField()
    roas_by_unit = serializers.ListField()
    operation_summary = serializers.DictField()


class DashboardSummaryResponseSerializer(serializers.Serializer):
    data = DashboardSummarySerializer()

    @staticmethod
    def from_filters(filters):
        return {"data": build_dashboard_summary(filters)}
