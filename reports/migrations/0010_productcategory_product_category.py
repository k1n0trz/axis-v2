from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0009_alter_businessunit_options_alter_channel_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=120, unique=True)),
                ("description", models.TextField(max_length=500)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Categoria de producto",
                "verbose_name_plural": "Categorias de producto",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="products", to="reports.productcategory"),
        ),
    ]
