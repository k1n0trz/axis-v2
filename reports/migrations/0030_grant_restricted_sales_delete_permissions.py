from django.db import migrations


def grant_restricted_sales_delete_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    grants = {
        "Marketplace": ["marketplacesale"],
        "Bali WhatsApp": ["baliwhatsappsale"],
    }
    for group_name, models in grants.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        permissions = []
        for model in models:
            content_type, _ = ContentType.objects.get_or_create(app_label="reports", model=model)
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"delete_{model}",
                defaults={"name": f"Can delete {model}"},
            )
            permissions.append(permission)
        group.permissions.add(*permissions)

        for user in group.user_set.all():
            user.user_permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0029_bali_whatsapp_group"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant_restricted_sales_delete_permissions, migrations.RunPython.noop),
    ]
