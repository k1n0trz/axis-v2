from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Attachment, MetricRecord, WeeklyTask
from .serializers import AttachmentSerializer, DashboardSummaryResponseSerializer, MetricRecordSerializer, WeeklyTaskSerializer
from .services.analytics import apply_attachment_filters, apply_metric_filters, apply_task_filters, build_filter_dict


class DashboardSummaryAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filters = build_filter_dict(request.GET)
        payload = DashboardSummaryResponseSerializer.from_filters(filters)
        return Response(payload)


class MetricRecordListAPIView(generics.ListAPIView):
    serializer_class = MetricRecordSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = MetricRecord.objects.select_related("business_unit", "country", "channel", "product")
        filters = build_filter_dict(self.request.GET)
        return apply_metric_filters(queryset, filters)


class WeeklyTaskListAPIView(generics.ListAPIView):
    serializer_class = WeeklyTaskSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = WeeklyTask.objects.select_related("business_unit", "country", "channel", "related_metric")
        filters = build_filter_dict(self.request.GET)
        return apply_task_filters(queryset, filters)


class AttachmentListAPIView(generics.ListAPIView):
    serializer_class = AttachmentSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Attachment.objects.select_related("business_unit", "country", "channel", "task")
        filters = build_filter_dict(self.request.GET)
        return apply_attachment_filters(queryset, filters)
