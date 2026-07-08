from datetime import time

from django.db import migrations


def set_default_due_time(apps, schema_editor):
    UserTask = apps.get_model("reports", "UserTask")
    UserTask.objects.filter(due_date__isnull=False, due_time__isnull=True).update(due_time=time(8, 0))


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0040_usertask_due_time"),
    ]

    operations = [
        migrations.RunPython(set_default_due_time, migrations.RunPython.noop),
    ]
