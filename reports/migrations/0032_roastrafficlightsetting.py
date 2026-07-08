from decimal import Decimal

from django.db import migrations, models


def seed_roas_setting(apps, schema_editor):
    RoasTrafficLightSetting = apps.get_model("reports", "RoasTrafficLightSetting")
    RoasTrafficLightSetting.objects.get_or_create(
        name="Semaforo ROAS",
        defaults={
            "green_min": Decimal("4.00"),
            "yellow_min": Decimal("3.00"),
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0031_operational_task_goal_completion_and_marketplace_ecuador"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoasTrafficLightSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(default="Semaforo ROAS", max_length=80, unique=True)),
                ("green_min", models.DecimalField(decimal_places=2, default=Decimal("4.00"), max_digits=6, verbose_name="Verde desde")),
                ("yellow_min", models.DecimalField(decimal_places=2, default=Decimal("3.00"), max_digits=6, verbose_name="Amarillo desde")),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Semaforo ROAS",
                "verbose_name_plural": "Semaforo ROAS",
                "ordering": ["-is_active", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="roastrafficlightsetting",
            constraint=models.CheckConstraint(condition=models.Q(("green_min__gte", 0)), name="reports_roas_green_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="roastrafficlightsetting",
            constraint=models.CheckConstraint(condition=models.Q(("yellow_min__gte", 0)), name="reports_roas_yellow_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="roastrafficlightsetting",
            constraint=models.CheckConstraint(condition=models.Q(("yellow_min__lte", models.F("green_min"))), name="reports_roas_threshold_order"),
        ),
        migrations.RunPython(seed_roas_setting, migrations.RunPython.noop),
    ]
