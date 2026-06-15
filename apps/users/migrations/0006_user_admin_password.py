"""Add admin_password field and backfill known seed credentials."""

from django.db import migrations, models


def backfill_admin_passwords(apps, schema_editor):
    User = apps.get_model("users", "User")
    known = {
        "admin@rocksolutions.co.tz": "Admin@2024",
        "driver@rocksolutions.co.tz": "Driver@2024",
        "storekeeper@rocksolutions.co.tz": "Storekeeper@2024",
        "gm@rocksolutions.co.tz": "GM@2024",
        "operator@rocksolutions.co.tz": "Operator@2024",
    }
    for email, password in known.items():
        User.objects.filter(email__iexact=email, admin_password="").update(admin_password=password)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_alter_permission_module"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="admin_password",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Last password set by an administrator (for credential export only).",
                max_length=128,
            ),
        ),
        migrations.RunPython(backfill_admin_passwords, migrations.RunPython.noop),
    ]
