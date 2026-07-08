from django.db import migrations


def assign_katerine_manager(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("reports", "UserProfile")

    katerine = User.objects.filter(username__iexact="Katerine").first()
    manager = User.objects.filter(username__iexact="EdiTrafficker").first()
    if not katerine or not manager:
        return

    profile, _ = UserProfile.objects.get_or_create(user=katerine)
    if profile.manager_id != manager.id:
        profile.manager = manager
        profile.save(update_fields=["manager", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0034_katerine_tasks_and_physical_store"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(assign_katerine_manager, migrations.RunPython.noop),
    ]
