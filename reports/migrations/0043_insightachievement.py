from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reports", "0042_rename_bali_visits_to_sessions"),
    ]

    operations = [
        migrations.CreateModel(
            name="InsightAchievement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("month", models.DateField()),
                (
                    "achievement_type",
                    models.CharField(
                        choices=[
                            ("sales_target", "Meta de ventas superada"),
                            ("sales_growth", "Crecimiento de ventas"),
                            ("spend_efficiency", "Reduccion eficiente de inversion"),
                            ("roas_growth", "Mejora de ROAS"),
                        ],
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(max_length=180)),
                ("description", models.TextField()),
                ("metric_value", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("delta_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("business_unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="insight_achievements", to="reports.businessunit")),
                ("channel", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="insight_achievements", to="reports.channel")),
                ("sales_target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="insight_achievements", to="reports.salestarget")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="insight_achievements", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Logro automatico",
                "verbose_name_plural": "Logros automaticos",
                "ordering": ["-month", "-metric_value", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="insightachievement",
            constraint=models.UniqueConstraint(fields=("sales_target", "month", "achievement_type"), name="reports_achievement_target_month_type_unique"),
        ),
        migrations.AddIndex(
            model_name="insightachievement",
            index=models.Index(fields=["user", "month"], name="rep_ach_user_month_idx"),
        ),
    ]
