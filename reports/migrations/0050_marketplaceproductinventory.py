from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0049_websitehealthcheck_accessibility_score_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketplaceProductInventory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("marketplace", models.CharField(default="mercadolibre", max_length=40)),
                ("item_id", models.CharField(max_length=60, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("sku", models.CharField(blank=True, max_length=120)),
                ("gtin", models.CharField(blank=True, max_length=80)),
                ("brand", models.CharField(blank=True, max_length=120)),
                ("model", models.CharField(blank=True, max_length=120)),
                ("category_id", models.CharField(blank=True, max_length=80)),
                ("status", models.CharField(blank=True, max_length=40)),
                ("permalink", models.URLField(blank=True, max_length=1000)),
                ("thumbnail_url", models.URLField(blank=True, max_length=1000)),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("available_quantity", models.IntegerField(default=0)),
                ("sold_quantity", models.IntegerField(default=0)),
                ("health_status", models.CharField(choices=[("ok", "Correcto"), ("warning", "Advertencia"), ("critical", "Critico")], default="ok", max_length=20)),
                ("warning_messages", models.JSONField(blank=True, default=list)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Inventario Marketplace",
                "verbose_name_plural": "Inventario Marketplace",
                "ordering": ["health_status", "status", "title"],
            },
        ),
        migrations.AddIndex(
            model_name="marketplaceproductinventory",
            index=models.Index(fields=["marketplace", "status"], name="reports_mar_market_6af5b1_idx"),
        ),
        migrations.AddIndex(
            model_name="marketplaceproductinventory",
            index=models.Index(fields=["marketplace", "sku"], name="reports_mar_market_74f5d8_idx"),
        ),
        migrations.AddIndex(
            model_name="marketplaceproductinventory",
            index=models.Index(fields=["marketplace", "health_status"], name="reports_mar_market_3e6db9_idx"),
        ),
        migrations.AddIndex(
            model_name="marketplaceproductinventory",
            index=models.Index(fields=["-last_synced_at"], name="reports_mar_last_sy_4ed0a6_idx"),
        ),
    ]
