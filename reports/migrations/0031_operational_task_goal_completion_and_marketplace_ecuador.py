from django.db import migrations, models


def seed_marketplace_ecuador_and_karen(apps, schema_editor):
    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    Channel = apps.get_model("reports", "Channel")
    Country = apps.get_model("reports", "Country")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("auth", "User")
    ContentType = apps.get_model("contenttypes", "ContentType")

    marketplace, _ = BusinessUnit.objects.get_or_create(
        slug="marketplace",
        defaults={"name": "Marketplace", "display_order": 3, "is_active": True},
    )
    if marketplace.name != "Marketplace":
        marketplace.name = "Marketplace"
        marketplace.is_active = True
        marketplace.save(update_fields=["name", "is_active", "updated_at"])

    ecuador, _ = Country.objects.get_or_create(
        code="EC",
        defaults={"name": "Ecuador", "display_order": 2, "is_active": True},
    )
    ecuador.name = "Ecuador"
    ecuador.is_active = True
    ecuador.save(update_fields=["name", "is_active", "updated_at"])
    ecuador.business_units.add(marketplace)

    colombia = Country.objects.filter(code="CO").first()
    if colombia:
        colombia.business_units.add(marketplace)

    channel = Channel.objects.filter(business_unit=marketplace, slug__in=("mercado-libre", "mercadolibre")).first()
    if channel:
        channel.name = "Mercadolibre"
        channel.slug = "mercado-libre"
        channel.display_order = 1
        channel.is_active = True
        channel.save(update_fields=["name", "slug", "display_order", "is_active", "updated_at"])
    else:
        Channel.objects.create(
            business_unit=marketplace,
            slug="mercado-libre",
            name="Mercadolibre",
            display_order=1,
            is_active=True,
        )

    group, _ = Group.objects.get_or_create(name="Marketplace")
    content_type, _ = ContentType.objects.get_or_create(app_label="reports", model="marketplacesale")
    permissions = []
    for action in ("view", "add", "change", "delete"):
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=f"{action}_marketplacesale",
            defaults={"name": f"Can {action} ventas marketplace"},
        )
        permissions.append(permission)
    group.permissions.add(*permissions)

    karen = User.objects.filter(username__iexact="Karen").first()
    if karen:
        karen.is_staff = True
        karen.save(update_fields=["is_staff"])
        karen.groups.add(group)
        karen.user_permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0030_grant_restricted_sales_delete_permissions"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationalgoaltask",
            name="goal_completion_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Porcentaje de cumplimiento que aporta o representa esta tarea operativa.",
                max_digits=5,
                null=True,
                verbose_name="% cumplimiento de meta",
            ),
        ),
        migrations.RunPython(seed_marketplace_ecuador_and_karen, migrations.RunPython.noop),
    ]
