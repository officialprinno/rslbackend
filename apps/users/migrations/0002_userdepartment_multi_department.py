# Generated manually for multi-department HOD support

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_user_departments(apps, schema_editor):
    User = apps.get_model("users", "User")
    UserDepartment = apps.get_model("users", "UserDepartment")
    for user in User.objects.filter(department_id__isnull=False, role_id__isnull=False):
        UserDepartment.objects.get_or_create(
            user_id=user.id,
            department_id=user.department_id,
            defaults={
                "role_id": user.role_id,
                "is_primary": True,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_multi_department",
            field=models.BooleanField(
                default=False,
                help_text="User manages multiple departments via user_departments",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="department",
            field=models.ForeignKey(
                blank=True,
                help_text="Primary department (display/default)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="users",
                to="users.department",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.ForeignKey(
                blank=True,
                help_text="Primary role (legacy; merged with user_departments at runtime)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="users",
                to="users.role",
            ),
        ),
        migrations.CreateModel(
            name="UserDepartment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_assignments",
                        to="users.department",
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_departments",
                        to="users.role",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="department_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-is_primary", "department__name"],
                "unique_together": {("user", "department")},
            },
        ),
        migrations.RunPython(backfill_user_departments, migrations.RunPython.noop),
    ]
