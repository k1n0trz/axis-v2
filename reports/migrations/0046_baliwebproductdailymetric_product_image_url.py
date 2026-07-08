from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0045_baliwebproductdailymetric"),
    ]

    operations = [
        migrations.AddField(
            model_name="baliwebproductdailymetric",
            name="product_image_url",
            field=models.URLField(blank=True, default="", max_length=1000),
        ),
    ]
