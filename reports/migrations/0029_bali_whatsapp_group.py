from django.db import migrations
from django.db.models import Q


def configure_bali_whatsapp_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    User = apps.get_model("auth", "User")
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    UserProfile = apps.get_model("reports", "UserProfile")

    group, _ = Group.objects.get_or_create(name="Bali WhatsApp")
    model_actions = {
        "baliwhatsappsale": ["add", "change", "view"],
        "operationalgoaltask": ["change", "view"],
    }
    permissions = []
    for model, actions in model_actions.items():
        content_type, _ = ContentType.objects.get_or_create(app_label="reports", model=model)
        for action in actions:
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"{action}_{model}",
                defaults={"name": f"Can {action} {model}"},
            )
            permissions.append(permission)
    group.permissions.add(*permissions)

    bali = BusinessUnit.objects.filter(slug="bali").first()
    alejo = User.objects.filter(Q(username__iexact="AlejoQ") | Q(email__iexact="alejandroq@helti.com.co")).first()
    estefy_users = User.objects.filter(Q(username__iexact="Estefy") | Q(email__icontains="estefy"))
    for user in estefy_users:
        user.is_active = True
        user.is_staff = True
        user.save(update_fields=["is_active", "is_staff"])
        user.groups.add(group)
        user.user_permissions.add(*permissions)
        profile, _ = UserProfile.objects.get_or_create(user_id=user.id)
        if alejo and not profile.manager_id:
            profile.manager = alejo
            profile.save(update_fields=["manager", "updated_at"])
        if bali:
            profile.business_units.add(bali)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0028_operationalgoaltaskattachment"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(configure_bali_whatsapp_group, migrations.RunPython.noop),
    ]
