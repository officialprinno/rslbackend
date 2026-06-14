# Sales order distribution workflow — Rock Solutions FMS

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_legacy_statuses(apps, schema_editor):
    SalesOrder = apps.get_model("sales", "SalesOrder")
    mapping = {
        "DRAFT": "NEW_ORDER",
        "CONFIRMED": "PAYMENT_CONFIRMED",
        "PROCESSING": "READY_FOR_DELIVERY",
        "PARTIAL": "IN_TRANSIT",
        "DELIVERED": "DELIVERY_CONFIRMED",
    }
    for old, new in mapping.items():
        SalesOrder.objects.filter(status=old).update(status=new)


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0003_alter_customer_country_alter_customer_credit_limit_and_more"),
        ("inventory", "0003_master_inventory_catalog"),
        ("procurement", "0001_initial"),
        ("logistics", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("NEW_ORDER", "New Order"),
                    ("STOCK_VERIFICATION", "Stock Verification"),
                    ("OUT_OF_STOCK", "Out of Stock"),
                    ("PENDING_DELIVERY_COST", "Pending Delivery Cost"),
                    ("DELIVERY_COST_CALC", "Delivery Cost Calculation"),
                    ("QUOTATION_PREP", "Quotation Preparation"),
                    ("QUOTATION_SENT", "Quotation Sent"),
                    ("WAITING_CUSTOMER", "Waiting Customer Response"),
                    ("QUOTATION_ACCEPTED", "Quotation Accepted"),
                    ("QUOTATION_REJECTED", "Quotation Rejected"),
                    ("INVOICE_GENERATED", "Invoice Generated"),
                    ("AWAITING_PAYMENT", "Awaiting Payment"),
                    ("PAYMENT_CONFIRMED", "Payment Confirmed"),
                    ("PAYMENT_FAILED", "Payment Verification Failed"),
                    ("READY_FOR_PICKUP", "Ready for Pickup"),
                    ("READY_FOR_DELIVERY", "Ready for Delivery"),
                    ("VEHICLE_ASSIGNED", "Vehicle Assigned"),
                    ("THIRD_PARTY_ASSIGNED", "Third Party Assigned"),
                    ("DISPATCHED", "Dispatched"),
                    ("IN_TRANSIT", "In Transit"),
                    ("DELIVERED", "Delivered"),
                    ("DELIVERY_CONFIRMED", "Delivery Confirmed"),
                    ("COMPLETED_PICKUP", "Completed — Customer Pickup"),
                    ("COMPLETED_COMPANY", "Completed — Company Delivery"),
                    ("COMPLETED_THIRD_PARTY", "Completed — Third Party"),
                    ("CANCELLED", "Cancelled"),
                    ("DRAFT", "Draft"),
                    ("CONFIRMED", "Confirmed"),
                    ("PROCESSING", "Processing"),
                    ("PARTIAL", "Partial"),
                ],
                default="NEW_ORDER",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="requested_delivery_location",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="fulfillment_warehouse",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales_orders",
                to="inventory.warehouse",
            ),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="inventory_status",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("RESERVED", "Reserved"),
                    ("LOCKED", "Locked"),
                    ("RELEASED", "Released"),
                ],
                default="NONE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="delivery_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PICKUP", "Customer Pickup"),
                    ("COMPANY", "Company Delivery"),
                    ("THIRD_PARTY", "Third Party Transport"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="delivery_cost",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="linked_pr",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sales_orders",
                to="procurement.purchaserequisition",
            ),
        ),
        migrations.AddField(
            model_name="salesorderitem",
            name="quantity_reserved",
            field=models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=18),
        ),
        migrations.AddField(
            model_name="salesorderitem",
            name="stock_available_snapshot",
            field=models.DecimalField(
                blank=True, decimal_places=4, max_digits=18, null=True
            ),
        ),
        migrations.AddField(
            model_name="salesorderactivity",
            name="previous_status",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="salesorderactivity",
            name="new_status",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="salesorderactivity",
            name="remarks",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="SalesOrderDeliveryCost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("delivery_distance_km", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=10)),
                ("transport_method", models.CharField(choices=[("ROAD", "Road"), ("RAIL", "Rail"), ("AIR", "Air")], default="ROAD", max_length=20)),
                ("vehicle_type", models.CharField(blank=True, max_length=50)),
                ("fuel_cost", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("loading_cost", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("offloading_cost", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("additional_charges", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("total_delivery_cost", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("notes", models.TextField(blank=True)),
                ("calculated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="delivery_costs_calculated", to=settings.AUTH_USER_MODEL)),
                ("sales_order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_cost_detail", to="sales.salesorder")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="SalesOrderPaymentProof",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("payment_method", models.CharField(choices=[("CASH", "Cash"), ("BANK_TRANSFER", "Bank Transfer"), ("CHEQUE", "Cheque"), ("MOBILE", "Mobile Money")], max_length=20)),
                ("reference_number", models.CharField(max_length=100)),
                ("proof_notes", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("VERIFIED", "Verified"), ("FAILED", "Failed")], default="PENDING", max_length=20)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.TextField(blank=True)),
                ("sales_order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payment_proofs", to="sales.salesorder")),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payment_proofs_submitted", to=settings.AUTH_USER_MODEL)),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payment_proofs_verified", to=settings.AUTH_USER_MODEL)),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="SalesOrderPickupDetail",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("pickup_date", models.DateField()),
                ("receiver_name", models.CharField(max_length=150)),
                ("receiver_phone", models.CharField(max_length=30)),
                ("signature_data", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pickups_recorded", to=settings.AUTH_USER_MODEL)),
                ("sales_order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pickup_detail", to="sales.salesorder")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="SalesOrderDispatchAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("assignment_type", models.CharField(choices=[("PICKUP", "Customer Pickup"), ("COMPANY", "Company Delivery"), ("THIRD_PARTY", "Third Party Transport")], max_length=20)),
                ("driver_phone", models.CharField(blank=True, max_length=30)),
                ("dispatch_date", models.DateField(blank=True, null=True)),
                ("transport_company", models.CharField(blank=True, max_length=255)),
                ("tracking_number", models.CharField(blank=True, max_length=100)),
                ("contact_person", models.CharField(blank=True, max_length=150)),
                ("contact_phone", models.CharField(blank=True, max_length=30)),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dispatch_assignments", to=settings.AUTH_USER_MODEL)),
                ("driver", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="so_assignments", to="logistics.driver")),
                ("sales_order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="dispatch_assignment", to="sales.salesorder")),
                ("vehicle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="so_assignments", to="logistics.vehicle")),
            ],
            options={"abstract": False},
        ),
        migrations.RunPython(migrate_legacy_statuses, migrations.RunPython.noop),
    ]
