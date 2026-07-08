from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0039_grant_editrafficker_bali_community_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="usertask",
            name="due_time",
            field=models.TimeField(blank=True, null=True, verbose_name="hora de cumplimiento"),
        ),
    ]
