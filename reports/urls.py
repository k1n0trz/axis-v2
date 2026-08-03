from django.urls import path

from . import api_views, views
from .ai import views as ai_views

app_name = "reports"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("uva/", views.uva_module, name="uva"),
    path("uva/comfama/", views.uva_comfama_module, name="uva_comfama"),
    path("uva/awn-internacional/", views.awn_internacional_module, name="awn_internacional"),
    path("bali/", views.bali_module, name="bali"),
    path("marketplace/", views.marketplace_module, name="marketplace"),
    path("distrisex/ecuador/", views.distrisex_ecuador_module, name="distrisex_ecuador"),
    path("webs/", views.websites_module, name="websites"),
    path("operation/", views.operation_weekly, name="operation"),
    path("files/", views.files_module, name="files"),
    path("excel/", views.excel_center, name="excel_center"),
    path("web-sales/", views.web_sales_report, name="web_sales"),
    path("ad-spend/", views.ad_spend_report, name="ad_spend"),
    path("excel/template/", views.export_master_template, name="excel_template"),
    path("excel/export/", views.export_master_data, name="excel_export"),
    path("settings/", views.settings_view, name="settings"),
    path("integrations/sync-now/", views.sync_external_data_now, name="sync_external_data_now"),
    path("integrations/sync-status/", views.sync_external_data_status, name="sync_external_data_status"),
    path("api/product-detail/", views.product_detail_api, name="product_detail_api"),
    path("api/uva/meta-ads-panel/", views.uva_meta_ads_panel_api, name="uva_meta_ads_panel_api"),
    path("api/dashboard/summary/", api_views.DashboardSummaryAPIView.as_view(), name="api_dashboard_summary"),
    path("api/metrics/", api_views.MetricRecordListAPIView.as_view(), name="api_metrics"),
    path("api/tasks/", api_views.WeeklyTaskListAPIView.as_view(), name="api_tasks"),
    path("api/ai/history/", ai_views.ai_history, name="ai_history"),
    path("api/ai/chat/", ai_views.ai_chat, name="ai_chat"),
    path("api/ai/memories/", ai_views.ai_memories, name="ai_memories"),
    path("api/ai/memories/<int:memory_id>/forget/", ai_views.ai_memory_forget, name="ai_memory_forget"),
    path("api/ai/feedback/", ai_views.ai_feedback, name="ai_feedback"),
    path("api/attachments/", api_views.AttachmentListAPIView.as_view(), name="api_attachments"),
]

