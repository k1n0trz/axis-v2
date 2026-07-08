from django.db import migrations, models


def grant_editrafficker_permissions(apps, schema_editor):
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
        "dailyproductcategorymetric": "metrica diaria por categoria",
        "dailyproductcategorysale": "venta diaria por categoria y canal",
        "comfamasale": "venta uva comfama",
        "comfamaadmetric": "pauta uva comfama",
        "awninternationalfollowermetric": "seguidores awn internacional",
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
    uva = BusinessUnit.objects.filter(slug="uva").first()
    if uva:
        profile.business_units.add(uva)


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0016_dailyproductcategorysale_exchange_rate_and_more"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="AwnInternationalFollowerMetric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("metric_date", models.DateField(help_text="Fecha diaria de la campaña de seguidores en Instagram.")),
                ("instagram_profile_visits", models.PositiveIntegerField(default=0, help_text="Visitas al perfil de Instagram registradas ese dia.")),
                ("new_followers", models.PositiveIntegerField(default=0, help_text="Seguidores nuevos conseguidos ese dia.")),
                ("spend_amount", models.DecimalField(decimal_places=2, default=0, help_text="Inversion diaria en COP.", max_digits=18)),
                ("cpr", models.DecimalField(decimal_places=2, default=0, help_text="Costo por resultado o visita al perfil, en COP.", max_digits=18)),
                ("cps", models.DecimalField(decimal_places=2, default=0, help_text="Costo por seguidor, en COP.", max_digits=18)),
                ("source_type", models.CharField(choices=[("manual", "Manual"), ("imported", "Importado")], default="imported", max_length=20)),
                ("source_file", models.CharField(blank=True, max_length=255)),
                ("source_row", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                ("country", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="awn_follower_metrics", to="reports.country")),
            ],
            options={
                "verbose_name": "Seguidores Awn Internacional",
                "verbose_name_plural": "Seguidores Awn Internacional",
                "ordering": ["-metric_date", "country__name"],
                "indexes": [models.Index(fields=["metric_date", "country"], name="rep_awn_date_ctry_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("country", "metric_date"), name="reports_awn_follower_metric_unique"),
                    models.CheckConstraint(condition=models.Q(instagram_profile_visits__gte=0), name="reports_awn_visits_nonnegative"),
                    models.CheckConstraint(condition=models.Q(new_followers__gte=0), name="reports_awn_followers_nonnegative"),
                    models.CheckConstraint(condition=models.Q(spend_amount__gte=0), name="reports_awn_spend_nonnegative"),
                    models.CheckConstraint(condition=models.Q(cpr__gte=0), name="reports_awn_cpr_nonnegative"),
                    models.CheckConstraint(condition=models.Q(cps__gte=0), name="reports_awn_cps_nonnegative"),
                ],
            },
        ),
        migrations.RunPython(grant_editrafficker_permissions, migrations.RunPython.noop),
    ]
