from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0044_remove_bali_daily_sales_nonnegative"),
    ]

    operations = [
        migrations.CreateModel(
            name="BaliWebProductDailyMetric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("metric_date", models.DateField()),
                ("product_title", models.CharField(max_length=255)),
                ("net_items_sold", models.IntegerField(default=0)),
                ("gross_sales", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("discounts", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("returns", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("net_sales", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("total_sales", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("source_file", models.CharField(blank=True, default="shopifyql", max_length=255)),
                ("business_unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bali_web_product_daily_metrics", to="reports.businessunit")),
                ("country", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bali_web_product_daily_metrics", to="reports.country")),
            ],
            options={
                "verbose_name": "Producto web diario Bali",
                "verbose_name_plural": "Productos web diarios Bali",
                "ordering": ["-metric_date", "product_title"],
                "indexes": [models.Index(fields=["metric_date", "business_unit", "country"], name="reports_bali_prod_d_bc_idx")],
                "constraints": [models.UniqueConstraint(fields=("business_unit", "country", "metric_date", "product_title"), name="reports_bali_web_product_daily_unique")],
            },
        ),
    ]
