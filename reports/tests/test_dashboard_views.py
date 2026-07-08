from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from reports import views
from reports.forms import ProfileForm
from reports.models import BaliDailyMetric, DailyChannelSale, InsightAchievement, MarketplaceProductInventory, SalesTarget, UserProfile
from reports.services.sales_dashboard import ensure_bali_catalogs, ensure_marketplace_catalogs, ensure_uva_catalogs


class DashboardViewRenderTests(TestCase):
    def setUp(self):
        ensure_uva_catalogs()
        ensure_bali_catalogs()
        ensure_marketplace_catalogs()
        self.user = User.objects.create_user(username="analyst", password="secret", is_staff=True)
        self.client.force_login(self.user)

    def test_dashboard_uva_and_bali_views_render(self):
        urls = [
            "/",
            "/uva/?date_start=2026-05-01&date_end=2026-05-15&business_unit=uva&country=CO",
            "/bali/?period_type=custom&date_start=2026-05-01&date_end=2026-05-15&business_unit=bali&country=CO&tab=web",
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive, nosnippet")
                self.assertIn("no-store", response["Cache-Control"])

    def test_general_sidebar_shows_webs_menu_item(self):
        response = self.client.get(reverse("reports:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("reports:websites"))
        self.assertContains(response, "Webs")

    def test_websites_history_filter_has_no_extra_submit_button(self):
        response = self.client.get(reverse("reports:websites"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historico de rendimiento")
        self.assertNotContains(response, "Ver historico")
        self.assertNotContains(response, "Escanear ahora")

    def test_global_sync_all_includes_websites_health(self):
        output = StringIO()

        call_command(
            "sync_axis_history_range",
            "--date-from",
            "2026-06-22",
            "--date-to",
            "2026-06-22",
            "--all",
            "--dry-run",
            stdout=output,
        )

        self.assertIn("websites-health", output.getvalue())

    def test_editrafficker_marketplace_user_sees_webs_menu_and_can_open_module(self):
        marketplace_group, _ = Group.objects.get_or_create(name=views.MARKETPLACE_GROUP)
        user = User.objects.create_user(username="EdiTrafficker", password="secret", is_staff=True)
        user.groups.add(marketplace_group)
        self.client.force_login(user)

        response = self.client.get(reverse("reports:marketplace"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("reports:websites"))
        self.assertContains(response, "Webs")

        response = self.client.get(reverse("reports:websites"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Webs")

    def test_bali_chart_uses_shared_cop_axis_for_sales_and_investment(self):
        catalogs = ensure_bali_catalogs()
        BaliDailyMetric.objects.create(
            business_unit=catalogs["business_unit"],
            country=catalogs["country"],
            metric_date=date(2026, 6, 4),
            web_sales_amount=Decimal("4760000.00"),
            web_order_count=25,
            google_spend_amount=Decimal("392003.00"),
            google_attributed_orders=7,
            whatsapp_conversations=20,
            cpa=Decimal("56273.00"),
            source_file="google-ads.xlsx",
        )

        response = self.client.get(
            "/bali/?period_type=custom&date_start=2026-06-04&date_end=2026-06-04&business_unit=bali&country=CO&tab=resumen"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ventas e inversion comparten la escala COP")
        self.assertContains(response, "392003")
        self.assertNotContains(response, "ySpend")

    def test_profile_form_saves_user_fields_and_valid_photo(self):
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc````\x00\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with TemporaryDirectory() as tmp_dir, self.settings(MEDIA_ROOT=tmp_dir):
            profile, _ = UserProfile.objects.get_or_create(user=self.user)
            form = ProfileForm(
                data={
                    "phone_number": "3001234567",
                    "first_name": "Edison",
                    "last_name": "Munera",
                    "email": "edison@example.com",
                },
                files={"photo": SimpleUploadedFile("avatar.png", png_bytes, content_type="image/png")},
                instance=profile,
                user=self.user,
            )

            self.assertTrue(form.is_valid(), form.errors)
            saved = form.save()
            self.user.refresh_from_db()

            self.assertEqual(self.user.first_name, "Edison")
            self.assertEqual(self.user.email, "edison@example.com")
            self.assertTrue(saved.photo.name.startswith("user_profiles/"))
            self.assertTrue((Path(tmp_dir) / saved.photo.name).exists())

    def test_profile_form_rejects_non_image_photo(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        form = ProfileForm(
            data={
                "phone_number": "3001234567",
                "first_name": "Edison",
                "last_name": "Munera",
                "email": "edison@example.com",
            },
            files={"photo": SimpleUploadedFile("avatar.svg", b"<svg></svg>", content_type="image/svg+xml")},
            instance=profile,
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("JPG o PNG", str(form.errors["photo"]))


class AdminSessionProtectionTests(TestCase):
    def test_admin_login_shows_helti_branding(self):
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "branding/logo-helti")
        self.assertContains(response, "branding/favicon")
        self.assertContains(response, "| Helti</title>")
        self.assertNotContains(response, "AXIS Admin")
        self.assertNotContains(response, "Admin Axis")
        self.assertNotContains(response, "Administracion Axis")

    def test_anonymous_dashboard_redirects_to_admin_login(self):
        response = self.client.get("/")

        self.assertRedirects(response, "/admin/login/?next=/", fetch_redirect_response=False)
        self.assertIn("no-store", response["Cache-Control"])

    def test_anonymous_api_does_not_return_data(self):
        response = self.client.get(reverse("reports:api_dashboard_summary"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Autenticacion de administrador requerida.")

    @override_settings(DEBUG=True)
    def test_anonymous_media_requires_admin_session_even_in_debug(self):
        response = self.client.get("/media/private-report.pdf")

        self.assertRedirects(response, "/admin/login/?next=/media/private-report.pdf", fetch_redirect_response=False)

    def test_authenticated_non_staff_user_cannot_view_reports(self):
        user = User.objects.create_user(username="regular", password="secret")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 403)

    def test_robots_disallows_indexing(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disallow: /")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive, nosnippet")


class ExternalSyncViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="editrafficker", password="secret", is_staff=True)
        self.client.force_login(self.user)

    @override_settings(DEBUG=False)
    @patch.object(views, "_trigger_cloud_run_sync_job", return_value={"operation_name": "operations/sync-123", "execution_name": "projects/p/locations/us-central1/jobs/j/executions/ex-123"})
    def test_external_sync_accepts_custom_ranges_longer_than_seven_days(self, trigger_job):
        response = self.client.post(
            reverse("reports:sync_external_data_now"),
            {
                "date_from": "2024-01-01",
                "date_to": "2024-01-20",
                "next": "/",
            },
        )

        self.assertEqual(response.status_code, 302)
        trigger_job.assert_called_once_with(date(2024, 1, 1), date(2024, 1, 20))

    @override_settings(DEBUG=False)
    @patch.object(views, "_trigger_cloud_run_sync_job", return_value={"operation_name": "operations/sync-123", "execution_name": "projects/p/locations/us-central1/jobs/j/executions/ex-123"})
    def test_external_sync_ajax_returns_polling_payload(self, trigger_job):
        response = self.client.post(
            reverse("reports:sync_external_data_now"),
            {
                "date_from": "2024-01-01",
                "date_to": "2024-01-20",
                "next": "/",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["execution_name"], "projects/p/locations/us-central1/jobs/j/executions/ex-123")
        self.assertEqual(payload["status_url"], reverse("reports:sync_external_data_status"))
        trigger_job.assert_called_once_with(date(2024, 1, 1), date(2024, 1, 20))

    @override_settings(DEBUG=False)
    @patch.object(views, "_trigger_cloud_run_sync_job")
    def test_external_sync_rejects_inverted_custom_range(self, trigger_job):
        response = self.client.post(
            reverse("reports:sync_external_data_now"),
            {
                "date_from": "2024-01-20",
                "date_to": "2024-01-01",
                "next": "/",
            },
        )

        self.assertEqual(response.status_code, 302)
        trigger_job.assert_not_called()

    @patch.object(
        views,
        "_cloud_run_api_get",
        return_value={
            "name": "projects/p/locations/us-central1/jobs/j/executions/ex-123",
            "conditions": [{"type": "Completed", "state": "CONDITION_SUCCEEDED", "message": "Execution completed successfully."}],
        },
    )
    def test_external_sync_status_reports_completed_execution(self, cloud_get):
        response = self.client.get(
            reverse("reports:sync_external_data_status"),
            {"execution": "projects/p/locations/us-central1/jobs/j/executions/ex-123"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["progress"], 100)
        cloud_get.assert_called_once_with("projects/p/locations/us-central1/jobs/j/executions/ex-123")

    @patch.object(
        views,
        "_cloud_run_api_get",
        return_value={
            "name": "projects/p/locations/us-central1/jobs/j/executions/ex-123",
            "completionTime": "2026-06-10T14:00:00Z",
            "conditions": [{"type": "Completed", "state": "CONDITION_PENDING", "message": "Waiting for execution to complete."}],
        },
    )
    def test_external_sync_status_uses_completion_time_as_completed(self, cloud_get):
        response = self.client.get(
            reverse("reports:sync_external_data_status"),
            {"execution": "projects/p/locations/us-central1/jobs/j/executions/ex-123"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["progress"], 100)

    @patch.object(
        views,
        "_cloud_run_api_get",
        return_value={
            "name": "projects/p/locations/us-central1/jobs/j/executions/ex-err",
            "conditions": [{"type": "Completed", "state": "CONDITION_FAILED", "message": "Task failed."}],
        },
    )
    def test_external_sync_status_reports_failed_execution(self, cloud_get):
        response = self.client.get(
            reverse("reports:sync_external_data_status"),
            {"execution": "projects/p/locations/us-central1/jobs/j/executions/ex-err"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["progress"], 100)
        self.assertEqual(payload["message"], "Task failed.")


class MarketplaceInsightAndAchievementTests(TestCase):
    def setUp(self):
        catalogs = ensure_marketplace_catalogs()
        self.unit = catalogs["business_unit"]
        self.country = catalogs["countries"]["CO"]
        self.channel = catalogs["channels"]["mercado-libre"]
        self.user = User.objects.create_user(username="market-owner", password="secret", is_staff=True)
        self.client.force_login(self.user)
        self.target = SalesTarget.objects.create(
            user=self.user,
            business_unit=self.unit,
            channel=self.channel,
            date_start=date(2026, 5, 1),
            date_end=date(2026, 5, 31),
            target_amount=Decimal("100000"),
        )
        DailyChannelSale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.channel,
            sale_date=date(2026, 4, 10),
            sales_amount=Decimal("80000"),
            spend_amount=Decimal("20000"),
            order_count=2,
        )
        DailyChannelSale.objects.create(
            business_unit=self.unit,
            country=self.country,
            channel=self.channel,
            sale_date=date(2026, 5, 10),
            sales_amount=Decimal("140000"),
            spend_amount=Decimal("15000"),
            order_count=3,
        )


    def test_marketplace_shows_mercadolibre_inventory_snapshot(self):
        MarketplaceProductInventory.objects.create(
            item_id="MCO123",
            title="Copa Uva Test",
            sku="SKU-123",
            gtin="7701234567890",
            brand="Uva",
            status="active",
            permalink="https://articulo.mercadolibre.com.co/MCO-123",
            available_quantity=7,
            sold_quantity=2,
            health_status=MarketplaceProductInventory.HealthStatus.OK,
            warning_messages=[],
        )

        response = self.client.get(
            "/marketplace/?period_type=custom&date_start=2026-05-01&date_end=2026-05-31&business_unit=marketplace&country=CO"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Inventario Mercado Libre")
        self.assertNotContains(response, "SKU-123")

        response = self.client.get(
            "/marketplace/?period_type=custom&date_start=2026-05-01&date_end=2026-05-31&business_unit=marketplace&country=CO&channel=mercado-libre"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventario Mercado Libre")
        self.assertContains(response, "SKU-123")
        self.assertContains(response, "7701234567890")

    def test_marketplace_shows_previous_period_comparison_and_smart_insights(self):
        response = self.client.get(
            "/marketplace/?period_type=custom&date_start=2026-05-01&date_end=2026-05-31&compare_mode=previous_period&business_unit=marketplace&country=CO"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vs. periodo anterior")
        self.assertContains(response, "Insights inteligentes del periodo")
        self.assertContains(response, "Ventas vs. periodo anterior")
        self.assertContains(response, "smart-insight-success")

    def test_goals_creates_green_monthly_achievements_automatically(self):
        response = self.client.get(
            "/metas/?period_type=custom&date_start=2026-05-01&date_end=2026-05-31&business_unit=marketplace&country=CO"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Logros del mes")
        self.assertContains(response, "Meta de ventas alcanzada")
        self.assertContains(response, "Aumento de ventas")
        self.assertTrue(
            InsightAchievement.objects.filter(
                user=self.user,
                month=date(2026, 5, 1),
                achievement_type=InsightAchievement.AchievementType.SALES_TARGET,
            ).exists()
        )
