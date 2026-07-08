from django.db import migrations


def grant_editrafficker_bali_permissions(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    UserProfile = apps.get_model("reports", "UserProfile")

    user = User.objects.filter(username__iexact="EdiTrafficker").first()
    if not user:
        return

    user.is_staff = True
    user.is_active = True
    user.save(update_fields=["is_staff", "is_active"])

    model_specs = {
        "balidailymetric": "metrica diaria bali",
        "baliwhatsappsale": "whatsapp bali",
    }
    actions = {
        "add": "Can add {}",
        "change": "Can change {}",
        "delete": "Can delete {}",
        "view": "Can view {}",
    }

    permissions = []
    for model, label in model_specs.items():
        content_type, _ = ContentType.objects.get_or_create(app_label="reports", model=model)
        for action, name_template in actions.items():
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"{action}_{model}",
                defaults={"name": name_template.format(label)},
            )
            permissions.append(permission)

    user.user_permissions.add(*permissions)

    profile, _ = UserProfile.objects.get_or_create(user_id=user.id)
    bali = BusinessUnit.objects.filter(slug="bali").first()
    if bali:
        profile.business_units.add(bali)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0021_baliwhatsappsale_balidailymetric"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant_editrafficker_bali_permissions, migrations.RunPython.noop),
    ]
