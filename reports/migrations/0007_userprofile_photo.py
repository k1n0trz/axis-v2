from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0006_adplatform_dailyadspend"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="photo",
            field=models.ImageField(blank=True, upload_to="user_profiles/"),
        ),
    ]
