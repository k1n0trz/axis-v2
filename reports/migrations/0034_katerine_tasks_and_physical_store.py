from django.db import migrations


def grant_katerine_task_access(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("reports", "UserProfile")

    katerine = User.objects.filter(username__iexact="Katerine").first()
    if not katerine:
        return

    katerine.is_staff = True
    katerine.is_active = True
    katerine.save(update_fields=["is_staff", "is_active"])

    permission_specs = (
        ("operationalgoaltask", "view", "Can view tarea"),
        ("operationalgoaltask", "change", "Can change tarea"),
        ("operationalgoaltaskattachment", "view", "Can view adjunto de tarea"),
        ("operationalgoaltaskattachment", "add", "Can add adjunto de tarea"),
        ("operationalgoaltaskattachment", "change", "Can change adjunto de tarea"),
        ("operationalgoaltaskattachment", "delete", "Can delete adjunto de tarea"),
    )
    task_permissions = []
    for model, action, name in permission_specs:
        content_type, _ = ContentType.objects.get_or_create(app_label="reports", model=model)
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=f"{action}_{model}",
            defaults={"name": name},
        )
        task_permissions.append(permission)
    katerine.user_permissions.add(*task_permissions)

    profile, _ = UserProfile.objects.get_or_create(user=katerine)
    business_units = BusinessUnit.objects.filter(slug__in=("marketplace", "bali"))
    profile.business_units.add(*business_units)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0033_baliphysicalstoresale"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(grant_katerine_task_access, migrations.RunPython.noop),
    ]
