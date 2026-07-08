from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0011_productcategory_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyProductCategoryMetric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("metric_date", models.DateField()),
                ("cpa_meta", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("cpa_google", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("spend_meta", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("spend_google", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("total_spend", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("sales_amount", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("notes", models.TextField(blank=True)),
                ("source_type", models.CharField(choices=[("manual", "Manual"), ("imported", "Importado")], default="imported", max_length=20)),
                ("source_file", models.CharField(blank=True, max_length=255)),
                ("business_unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="daily_product_category_metrics", to="reports.businessunit")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="daily_metrics", to="reports.productcategory")),
                ("country", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="daily_product_category_metrics", to="reports.country")),
            ],
            options={
                "verbose_name": "Metrica diaria por categoria",
                "verbose_name_plural": "Metricas diarias por categoria",
                "ordering": ["-metric_date", "category__name"],
            },
        ),
        migrations.AddIndex(
            model_name="dailyproductcategorymetric",
            index=models.Index(fields=["metric_date", "business_unit", "country", "category"], name="reports_dai_metric__c5542d_idx"),
        ),
        migrations.AddConstraint(
            model_name="dailyproductcategorymetric",
            constraint=models.UniqueConstraint(fields=("business_unit", "country", "category", "metric_date"), name="reports_daily_product_category_metric_unique"),
        ),
    ]
