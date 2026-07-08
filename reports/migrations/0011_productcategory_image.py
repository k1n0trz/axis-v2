from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0010_productcategory_product_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="productcategory",
            name="image",
            field=models.FileField(blank=True, upload_to="product_categories/"),
        ),
    ]
