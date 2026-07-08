from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


ECUADOR_USD_TO_COP_RATE = Decimal("3700")
MONEY_QUANT = Decimal("0.01")


def _merge_text(left, right):
    parts = []
    for value in (left, right):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return " | ".join(parts)


def _move_category_sales(apps, old_category, new_category):
    DailyProductCategorySale = apps.get_model("reports", "DailyProductCategorySale")
    rows = DailyProductCategorySale.objects.filter(
        country__code="CO",
        category=old_category,
        notes__icontains="sin adhesiv",
    )
    for row in list(rows):
        target = (
            DailyProductCategorySale.objects.filter(
                business_unit_id=row.business_unit_id,
                country_id=row.country_id,
                channel_id=row.channel_id,
                category=new_category,
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
            row.category_id = new_category.id
            row.save()


def _move_category_metrics(apps, old_category, new_category):
    DailyProductCategoryMetric = apps.get_model("reports", "DailyProductCategoryMetric")
    rows = DailyProductCategoryMetric.objects.filter(
        country__code="CO",
        category=old_category,
        notes__icontains="sin adhesiv",
    )
    for row in list(rows):
        target = (
            DailyProductCategoryMetric.objects.filter(
                business_unit_id=row.business_unit_id,
                country_id=row.country_id,
                category=new_category,
                metric_date=row.metric_date,
            )
            .exclude(pk=row.pk)
            .first()
        )
        if target:
            target.spend_meta = (target.spend_meta or Decimal("0")) + (row.spend_meta or Decimal("0"))
            target.spend_google = (target.spend_google or Decimal("0")) + (row.spend_google or Decimal("0"))
            target.sales_amount = (target.sales_amount or Decimal("0")) + (row.sales_amount or Decimal("0"))
            target.cpa_meta = target.cpa_meta or row.cpa_meta
            target.cpa_google = target.cpa_google or row.cpa_google
            target.notes = _merge_text(target.notes, row.notes)
            target.save()
            row.delete()
        else:
            row.category_id = new_category.id
            row.save()


def forwards(apps, schema_editor):
    ProductCategory = apps.get_model("reports", "ProductCategory")
    DailyProductCategorySale = apps.get_model("reports", "DailyProductCategorySale")

    old_category = ProductCategory.objects.filter(slug="cubrepezones").first()
    new_category, _ = ProductCategory.objects.get_or_create(
        slug="cubrepezones-sin-adhesivo",
        defaults={
            "name": "Cubrepezones sin adhesivo",
            "description": "Categoria separada de Cubrepezones Colombia sin adhesivo.",
            "is_active": True,
        },
    )
    if old_category:
        _move_category_sales(apps, old_category, new_category)
        _move_category_metrics(apps, old_category, new_category)

    for row in DailyProductCategorySale.objects.filter(country__code="EC", original_currency__iexact="USD"):
        original_amount = row.original_amount or Decimal("0")
        row.exchange_rate = ECUADOR_USD_TO_COP_RATE
        row.sales_amount = (original_amount * ECUADOR_USD_TO_COP_RATE).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        row.save()


def backwards(apps, schema_editor):
    DailyProductCategorySale = apps.get_model("reports", "DailyProductCategorySale")
    ProductCategory = apps.get_model("reports", "ProductCategory")
    old_category = ProductCategory.objects.filter(slug="cubrepezones").first()
    new_category = ProductCategory.objects.filter(slug="cubrepezones-sin-adhesivo").first()
    if old_category and new_category:
        DailyProductCategorySale.objects.filter(category=new_category).update(category=old_category)


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0046_baliwebproductdailymetric_product_image_url"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
