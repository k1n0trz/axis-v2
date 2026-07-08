from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0007_userprofile_photo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="photo",
            field=models.FileField(blank=True, upload_to="user_profiles/"),
        ),
    ]
