# Master inventory catalogue — category codes and SERVICE item type

from django.db import migrations, models


def backfill_category_codes(apps, schema_editor):
    ItemCategory = apps.get_model("inventory", "ItemCategory")
    for category in ItemCategory.objects.filter(code=""):
        slug = category.name.upper().replace(" ", "-")[:10]
        base = slug or "CAT"
        code = base
        suffix = 1
        while ItemCategory.objects.filter(code=code).exclude(pk=category.pk).exists():
            code = f"{base[:7]}{suffix}"
            suffix += 1
        category.code = code
        category.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_extended_inventory"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcategory",
            name="code",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.RunPython(backfill_category_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="itemcategory",
            name="code",
            field=models.CharField(blank=True, default="", max_length=10, unique=True),
        ),
        migrations.AlterField(
            model_name="item",
            name="item_type",
            field=models.CharField(
                choices=[
                    ("TRADED", "Traded"),
                    ("RAW_MATERIAL", "Raw Material"),
                    ("WORK_IN_PROGRESS", "Work in Progress"),
                    ("FINISHED_GOODS", "Finished Goods"),
                    ("MANUFACTURED", "Manufactured"),
                    ("PPE", "PPE"),
                    ("SPARE_PART", "Spare Part"),
                    ("ASSET", "Asset"),
                    ("SERVICE", "Service"),
                ],
                max_length=20,
            ),
        ),
    ]
