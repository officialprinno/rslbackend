# Generated manually for extended inventory module

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
        ("procurement", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="subcategory",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="item",
            name="has_batch_tracking",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="item",
            name="minimum_stock",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="maximum_stock",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="safety_stock",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="item",
            name="lead_time_days",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="item",
            name="preferred_supplier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="preferred_items",
                to="procurement.supplier",
            ),
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
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="warehouse",
            name="warehouse_type",
            field=models.CharField(
                choices=[
                    ("RAW_MATERIAL", "Raw Material Warehouse"),
                    ("FINISHED_GOODS", "Finished Goods Warehouse"),
                    ("MINING_CONSUMABLES", "Mining Consumables Warehouse"),
                    ("PPE", "PPE Warehouse"),
                    ("SPARE_PARTS", "Spare Parts Warehouse"),
                    ("TRANSIT", "Transit Warehouse"),
                ],
                default="MINING_CONSUMABLES",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="warehouse",
            name="capacity",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="movement_type",
            field=models.CharField(
                choices=[
                    ("IN", "In"),
                    ("OUT", "Out"),
                    ("TRANSFER", "Transfer"),
                    ("ADJUSTMENT", "Adjustment"),
                    ("PRODUCTION_CONSUMPTION", "Production Consumption"),
                    ("PRODUCTION_OUTPUT", "Production Output"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="stockadjustment",
            name="adjustment_type",
            field=models.CharField(
                choices=[
                    ("INCREASE", "Increase"),
                    ("DECREASE", "Decrease"),
                    ("DAMAGE", "Damage"),
                    ("LOSS", "Loss"),
                    ("WRITE_OFF", "Write Off"),
                    ("PHYSICAL_COUNT", "Physical Count Difference"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="itemserialnumber",
            name="manufacturer_serial",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="itemserialnumber",
            name="purchase_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="itemserialnumber",
            name="warranty_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="stockalert",
            name="alert_type",
            field=models.CharField(
                choices=[
                    ("LOW_STOCK", "Low Stock"),
                    ("OUT_OF_STOCK", "Out of Stock"),
                    ("EXPIRY_SOON", "Expiry Soon"),
                    ("OVERSTOCK", "Overstock"),
                    ("NEGATIVE_STOCK", "Negative Stock"),
                    ("PENDING_APPROVAL", "Pending Approval"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="StockBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("batch_number", models.CharField(max_length=100)),
                ("manufacture_date", models.DateField(blank=True, null=True)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("quantity", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("unit_cost", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="batches", to="inventory.item")),
                ("supplier", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_batches", to="procurement.supplier")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="batches", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("item", "warehouse", "batch_number")}},
        ),
        migrations.CreateModel(
            name="StockTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("transfer_number", models.CharField(editable=False, max_length=30, unique=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("COMPLETED", "Completed"), ("REJECTED", "Rejected")], default="PENDING", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_transfers_approved", to=settings.AUTH_USER_MODEL)),
                ("destination_warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers_in", to="inventory.warehouse")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_transfers_requested", to=settings.AUTH_USER_MODEL)),
                ("source_warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers_out", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StockTransferLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfer_lines", to="inventory.item")),
                ("transfer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="inventory.stocktransfer")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="DepartmentRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("request_number", models.CharField(editable=False, max_length=30, unique=True)),
                ("department", models.CharField(choices=[("PRODUCTION", "Production"), ("PROCUREMENT", "Procurement"), ("HSE", "HSE"), ("LOGISTICS", "Logistics"), ("MAINTENANCE", "Maintenance"), ("ADMINISTRATION", "Administration")], max_length=30)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("ISSUED", "Issued"), ("REJECTED", "Rejected")], default="PENDING", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="department_requests_approved", to=settings.AUTH_USER_MODEL)),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="department_requests_created", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="department_requests", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="DepartmentRequestLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="dept_request_lines", to="inventory.item")),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="inventory.departmentrequest")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="GoodsIssueNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("gin_number", models.CharField(editable=False, max_length=30, unique=True)),
                ("department", models.CharField(choices=[("PRODUCTION", "Production"), ("MAINTENANCE", "Maintenance"), ("HSE", "HSE"), ("LOGISTICS", "Logistics"), ("SALES", "Sales")], max_length=30)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="PENDING", max_length=20)),
                ("reason", models.TextField(blank=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gins_approved", to=settings.AUTH_USER_MODEL)),
                ("department_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="goods_issue_notes", to="inventory.departmentrequest")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gins_requested", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="goods_issue_notes", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GoodsIssueLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("gin", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="inventory.goodsissuenote")),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gin_lines", to="inventory.item")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="StockTake",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("take_number", models.CharField(editable=False, max_length=30, unique=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="PENDING", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_takes_approved", to=settings.AUTH_USER_MODEL)),
                ("conducted_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_takes_conducted", to=settings.AUTH_USER_MODEL)),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_takes", to="inventory.warehouse")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StockTakeLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("system_quantity", models.DecimalField(decimal_places=4, max_digits=18)),
                ("physical_quantity", models.DecimalField(decimal_places=4, max_digits=18)),
                ("variance", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=18)),
                ("reason", models.TextField(blank=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_take_lines", to="inventory.item")),
                ("stock_take", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="inventory.stocktake")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
