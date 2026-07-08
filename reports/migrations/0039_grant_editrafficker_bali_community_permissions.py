from django.db import migrations


def grant_editrafficker_bali_community_permissions(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    UserProfile = apps.get_model("reports", "UserProfile")

    content_type, _ = ContentType.objects.get_or_create(app_label="reports", model="balicommunitywebcammetric")
    permissions = []
    for action in ("add", "change", "view", "delete"):
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=f"{action}_balicommunitywebcammetric",
            defaults={"name": f"Can {action} comunidad webcam bali"},
        )
        permissions.append(permission)

    group = Group.objects.filter(name="Bali WhatsApp").first()
    if group:
        group.permissions.add(*permissions)

    user = User.objects.filter(username__iexact="EdiTrafficker").first()
    if not user:
        return

    user.is_staff = True
    user.is_active = True
    user.save(update_fields=["is_staff", "is_active"])
    user.user_permissions.add(*permissions)

    profile, _ = UserProfile.objects.get_or_create(user_id=user.id)
    bali = BusinessUnit.objects.filter(slug="bali").first()
    if bali:
        profile.business_units.add(bali)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0038_balicommunitywebcammetric"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(grant_editrafficker_bali_community_permissions, migrations.RunPython.noop),
    ]
