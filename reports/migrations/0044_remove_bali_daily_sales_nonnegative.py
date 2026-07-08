from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0043_insightachievement"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="balidailymetric",
            name="reports_bali_daily_sales_nonnegative",
        ),
    ]
