"""Internal consumption enhancements — item_usage, dept request workflow, GIN issue_type."""

from decimal import Decimal

from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def copy_quantity_to_requested_qty(apps, schema_editor):
    DepartmentRequestLine = apps.get_model("inventory", "DepartmentRequestLine")
    for line in DepartmentRequestLine.objects.all():
        if line.requested_qty is None:
            line.requested_qty = line.quantity
            line.save(update_fields=["requested_qty"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_master_inventory_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="item",
            name="item_usage",
            field=models.CharField(
                choices=[
                    ("FOR_SALE", "For Sale"),
                    ("INTERNAL_USE", "Internal Use"),
                    ("BOTH", "Both"),
                ],
                default="BOTH",
                help_text="Commercial sales, internal consumption, or both.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="departmentrequest",
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
            model_name="departmentrequest",
            name="purpose",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="departmentrequest",
            name="needed_by_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="departmentrequest",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="departmentrequest",
            name="approval_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="departmentrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("PROCESSING", "Processing"),
                    ("ISSUED", "Issued"),
                    ("PARTIALLY_ISSUED", "Partially Issued"),
                    ("REJECTED", "Rejected"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="departmentrequestline",
            name="requested_qty",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=18,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))],
            ),
        ),
        migrations.AddField(
            model_name="departmentrequestline",
            name="issued_qty",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="departmentrequestline",
            name="warehouse",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dept_request_lines",
                to="inventory.warehouse",
            ),
        ),
        migrations.AddField(
            model_name="departmentrequestline",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="goodsissuenote",
            name="issue_type",
            field=models.CharField(
                choices=[
                    ("SALES", "Sales"),
                    ("INTERNAL", "Internal"),
                    ("PRODUCTION", "Production"),
                    ("TRANSFER", "Transfer"),
                ],
                default="INTERNAL",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="reference_type",
            field=models.CharField(
                choices=[
                    ("GRN", "GRN"),
                    ("GIN", "GIN"),
                    ("DEPT_REQUEST", "Department Request"),
                    ("SALES_ORDER", "Sales Order"),
                    ("WORK_ORDER", "Work Order"),
                    ("TRANSFER", "Transfer"),
                    ("ADJUSTMENT", "Adjustment"),
                    ("MANUAL", "Manual"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(copy_quantity_to_requested_qty, migrations.RunPython.noop),
    ]
