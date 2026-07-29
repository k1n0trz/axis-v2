from decimal import Decimal

from django.db import migrations


def _merge_text(left, right):
    parts = []
    for value in (left, right):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return " | ".join(parts)


def _merge_sales(apps, source_category, target_category):
    DailyProductCategorySale = apps.get_model("reports", "DailyProductCategorySale")
    rows = DailyProductCategorySale.objects.filter(category=source_category)
    for row in list(rows):
        target = (
            DailyProductCategorySale.objects.filter(
                business_unit_id=row.business_unit_id,
                country_id=row.country_id,
                channel_id=row.channel_id,
                category=target_category,
                sale_date=row.sale_date,
            )
            .exclude(pk=row.pk)
            .first()
        )
        if target:
            target.sales_amount = (target.sales_amount or Decimal("0")) + (row.sales_amount or Decimal("0"))
            target.original_amount = (target.original_amount or Decimal("0")) + (row.original_amount or Decimal("0"))
            target.quantity = (target.quantity or 0) + (row.quantity or 0)
            target.notes = _merge_text(target.notes, row.notes)
            target.save()
            row.delete()
        else:
            row.category_id = target_category.id
            row.save()


def _merge_metrics(apps, source_category, target_category):
    DailyProductCategoryMetric = apps.get_model("reports", "DailyProductCategoryMetric")
    rows = DailyProductCategoryMetric.objects.filter(category=source_category)
    for row in list(rows):
        target = (
            DailyProductCategoryMetric.objects.filter(
                business_unit_id=row.business_unit_id,
                country_id=row.country_id,
                category=target_category,
                metric_date=row.metric_date,
            )
            .exclude(pk=row.pk)
            .first()
        )
        if target:
            target.spend_meta = (target.spend_meta or Decimal("0")) + (row.spend_meta or Decimal("0"))
            target.spend_google = (target.spend_google or Decimal("0")) + (row.spend_google or Decimal("0"))
            target.total_spend = (target.spend_meta or Decimal("0")) + (target.spend_google or Decimal("0"))
            target.sales_amount = (target.sales_amount or Decimal("0")) + (row.sales_amount or Decimal("0"))
            target.cpa_meta = target.cpa_meta or row.cpa_meta
            target.cpa_google = target.cpa_google or row.cpa_google
            target.notes = _merge_text(target.notes, row.notes)
            target.save()
            row.delete()
        else:
            row.category_id = target_category.id
            row.save()


def forwards(apps, schema_editor):
    ProductCategory = apps.get_model("reports", "ProductCategory")
    target, _ = ProductCategory.objects.get_or_create(
        slug="cubrepezones",
        defaults={
            "name": "Cubrepezones",
            "description": "Categoria unificada de cubrepezones Uva.",
            "is_active": True,
        },
    )
    source = ProductCategory.objects.filter(slug="cubrepezones-sin-adhesivo").first()
    if not source:
        return
    _merge_sales(apps, source, target)
    _merge_metrics(apps, source, target)
    source.is_active = False
    source.description = _merge_text(source.description, "Unificada en Cubrepezones.")
    source.save(update_fields=["is_active", "description", "updated_at"])


def backwards(apps, schema_editor):
    ProductCategory = apps.get_model("reports", "ProductCategory")
    source, _ = ProductCategory.objects.get_or_create(
        slug="cubrepezones-sin-adhesivo",
        defaults={
            "name": "Cubrepezones sin adhesivo",
            "description": "Categoria separada de cubrepezones sin adhesivo.",
            "is_active": True,
        },
    )
    source.is_active = True
    source.save(update_fields=["is_active", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0051_dailygeoadmetric_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
