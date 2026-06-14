"""Machine operator execution workflow — additive fields and models."""

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_internal_consumption"),
        ("production", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("APPROVED", "Approved"),
                    ("ASSIGNED", "Assigned"),
                    ("IN_PROGRESS", "In Progress"),
                    ("PAUSED", "Paused"),
                    ("COMPLETED_PENDING", "Pending Production Approval"),
                    ("PROD_APPROVED", "Production Approved"),
                    ("WAITING_STORE", "Waiting Store Receipt"),
                    ("INV_RECEIVED", "Inventory Received"),
                    ("CLOSED", "Closed"),
                    ("COMPLETED", "Completed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="DRAFT",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="workorder",
            name="assigned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workorder",
            name="completion_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="workorder",
            name="execution_workflow",
            field=models.BooleanField(
                default=False,
                help_text="When true, inventory moves only after production approval and store receipt.",
            ),
        ),
        migrations.AddField(
            model_name="workorder",
            name="machine_condition",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="workorder",
            name="priority",
            field=models.CharField(
                choices=[
                    ("LOW", "Low"),
                    ("MEDIUM", "Medium"),
                    ("HIGH", "High"),
                    ("URGENT", "Urgent"),
                ],
                default="MEDIUM",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="workorder",
            name="production_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workorder",
            name="production_approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="work_orders_production_approved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workorder",
            name="production_line",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="workorder",
            name="store_received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workorder",
            name="store_received_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="work_orders_store_received",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="machine",
            name="runtime_condition",
            field=models.CharField(
                blank=True,
                choices=[
                    ("RUNNING", "Running"),
                    ("IDLE", "Idle"),
                    ("MAINTENANCE_REQUIRED", "Maintenance Required"),
                    ("BREAKDOWN", "Breakdown"),
                ],
                default="IDLE",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="machine",
            name="runtime_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="machine",
            name="runtime_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="machine",
            name="runtime_updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="machine_runtime_updates",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="WorkOrderPendingMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity_consumed", models.DecimalField(decimal_places=4, max_digits=18)),
                ("waste_quantity", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=18)),
                ("posted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="production_pending_materials",
                        to="inventory.item",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="production_pending_materials_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_materials",
                        to="production.workorder",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="WorkOrderProgressEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity_produced", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=18)),
                ("quantity_defective", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=18)),
                ("progress_percent", models.DecimalField(decimal_places=1, default=Decimal("0"), max_digits=5)),
                ("machine_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="production_progress_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="progress_entries",
                        to="production.workorder",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="WorkOrderPauseRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.TextField()),
                ("paused_at", models.DateTimeField()),
                ("resumed_at", models.DateTimeField(blank=True, null=True)),
                ("downtime_minutes", models.DecimalField(decimal_places=1, default=Decimal("0"), max_digits=10)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="production_pause_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pause_records",
                        to="production.workorder",
                    ),
                ),
            ],
            options={"ordering": ["-paused_at"]},
        ),
        migrations.CreateModel(
            name="WorkOrderExecutionEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("START", "Start"),
                            ("PAUSE", "Pause"),
                            ("RESUME", "Resume"),
                            ("PROGRESS", "Progress"),
                            ("CONSUMPTION", "Consumption"),
                            ("SUBMIT_COMPLETION", "Submit Completion"),
                            ("MACHINE_STATUS", "Machine Status"),
                            ("ASSIGN", "Assign Operator"),
                            ("PROD_APPROVE", "Production Approve"),
                            ("STORE_RECEIPT", "Store Receipt"),
                        ],
                        max_length=30,
                    ),
                ),
                ("old_status", models.CharField(blank=True, max_length=30)),
                ("new_status", models.CharField(blank=True, max_length=30)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="production_execution_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "work_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="execution_events",
                        to="production.workorder",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="FinishedGoodsReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("quantity_received", models.DecimalField(decimal_places=4, max_digits=18)),
                ("batch_number", models.CharField(blank=True, max_length=30)),
                ("notes", models.TextField(blank=True)),
                ("posted", models.BooleanField(default=False)),
                (
                    "received_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="finished_goods_receipts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "warehouse",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="finished_goods_receipts",
                        to="inventory.warehouse",
                    ),
                ),
                (
                    "work_order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="finished_goods_receipt",
                        to="production.workorder",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
