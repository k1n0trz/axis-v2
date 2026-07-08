from django.db import migrations


def grant_editrafficker_product_category_permissions(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    user = User.objects.filter(username__iexact="EdiTrafficker").first()
    if not user:
        return

    user.is_staff = True
    user.is_active = True
    user.save(update_fields=["is_staff", "is_active"])

    content_type, _ = ContentType.objects.get_or_create(app_label="reports", model="productcategory")
    actions = {
        "add": "Can add Categoria de producto",
        "change": "Can change Categoria de producto",
        "view": "Can view Categoria de producto",
    }
    permissions = []
    for action, name in actions.items():
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=f"{action}_productcategory",
            defaults={"name": name},
        )
        permissions.append(permission)

    user.user_permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0017_awninternationalfollowermetric_and_permissions"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant_editrafficker_product_category_permissions, migrations.RunPython.noop),
    ]
