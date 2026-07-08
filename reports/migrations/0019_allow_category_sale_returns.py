from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0018_grant_editrafficker_product_category_permissions"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="dailyproductcategorysale",
            name="reports_daily_product_category_sale_amount_nonnegative",
        ),
        migrations.RemoveConstraint(
            model_name="dailyproductcategorysale",
            name="reports_daily_product_category_sale_original_nonnegative",
        ),
        migrations.RemoveConstraint(
            model_name="dailyproductcategorysale",
            name="reports_daily_product_category_sale_qty_nonnegative",
        ),
        migrations.AlterField(
            model_name="dailyproductcategorysale",
            name="quantity",
            field=models.IntegerField(default=0),
        ),
    ]
