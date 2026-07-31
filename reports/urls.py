from django.urls import path

from . import api_views, views

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
    path("tareas/", views.tasks_dashboard, name="tasks"),
    path("tareas/crear/", views.create_user_task_from_calendar, name="task_calendar_create"),
    path("tareas/agentes/exportar/", views.export_agent_tasks, name="task_agents_export"),
    path("tareas/<int:pk>/actualizar/", views.update_user_task_from_calendar, name="task_calendar_update"),
    path("tareas/<int:pk>/mover/", views.update_user_task_schedule, name="task_calendar_move"),
    path("tareas/<int:pk>/estado/", views.update_user_task_status, name="task_calendar_status"),
    path("metas/", views.goals_dashboard, name="goals"),
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
    path("operational-tasks/<int:pk>/update/", views.update_operational_task, name="operational_task_update"),
    path("api/dashboard/summary/", api_views.DashboardSummaryAPIView.as_view(), name="api_dashboard_summary"),
    path("api/metrics/", api_views.MetricRecordListAPIView.as_view(), name="api_metrics"),
    path("api/tasks/", api_views.WeeklyTaskListAPIView.as_view(), name="api_tasks"),
    path("api/attachments/", api_views.AttachmentListAPIView.as_view(), name="api_attachments"),
]

