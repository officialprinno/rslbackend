from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("logistics", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="driver",
            name="assigned_vehicle",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_drivers",
                to="logistics.vehicle",
            ),
        ),
        migrations.AddField(
            model_name="driver",
            name="availability_status",
            field=models.CharField(
                choices=[
                    ("AVAILABLE", "Available"),
                    ("ON_DELIVERY", "On Delivery"),
                    ("RETURNING", "Returning"),
                    ("OFF_DUTY", "Off Duty"),
                ],
                default="AVAILABLE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="driver",
            name="employee_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="arrived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="fuel_remaining",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="logistics_review_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending Review"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="odometer_end",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="odometer_start",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="return_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="return_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="trip_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="trip_status",
            field=models.CharField(
                choices=[
                    ("ASSIGNED", "Assigned"),
                    ("STARTED", "Started"),
                    ("IN_TRANSIT", "In Transit"),
                    ("ARRIVED", "Arrived"),
                    ("DELIVERED", "Delivered"),
                    ("RETURNING", "Returning"),
                    ("RETURN_CONFIRMED", "Return Confirmed"),
                ],
                default="ASSIGNED",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="vehicle_condition_end",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="deliveryorder",
            name="vehicle_condition_start",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="status",
            field=models.CharField(
                choices=[
                    ("AVAILABLE", "Available"),
                    ("ON_TRIP", "On Trip"),
                    ("IN_USE", "In Use"),
                    ("RETURNING", "Returning"),
                    ("MAINTENANCE", "Maintenance"),
                    ("BREAKDOWN", "Breakdown"),
                    ("OUT_OF_SERVICE", "Out of Service"),
                ],
                default="AVAILABLE",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DeliveryConfirmation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("receiver_name", models.CharField(max_length=150)),
                ("receiver_position", models.CharField(blank=True, max_length=150)),
                ("receiver_phone", models.CharField(blank=True, max_length=30)),
                ("receiver_company", models.CharField(blank=True, max_length=255)),
                (
                    "quantity_delivered",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0"))
                        ],
                    ),
                ),
                ("delivery_notes", models.TextField(blank=True)),
                ("signature_data", models.TextField(blank=True)),
                ("proof_photo_url", models.URLField(blank=True)),
                ("proof_document_url", models.URLField(blank=True)),
                (
                    "confirmed_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="delivery_confirmations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "delivery_order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="confirmation",
                        to="logistics.deliveryorder",
                    ),
                ),
            ],
            options={
                "ordering": ["-confirmed_at"],
            },
        ),
        migrations.CreateModel(
            name="DeliveryTripEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("action", models.CharField(max_length=80)),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(blank=True, max_length=20)),
                ("details", models.TextField(blank=True)),
                (
                    "delivery_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trip_events",
                        to="logistics.deliveryorder",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="delivery_trip_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="VehicleConditionReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "condition",
                    models.CharField(
                        choices=[
                            ("GOOD", "Good"),
                            ("MINOR_ISSUE", "Minor Issue"),
                            ("MAINTENANCE_REQUIRED", "Maintenance Required"),
                            ("BREAKDOWN", "Breakdown"),
                        ],
                        max_length=30,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("odometer_reading", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "fuel_remaining",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0"))
                        ],
                    ),
                ),
                ("photo_url", models.URLField(blank=True)),
                (
                    "delivery_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="condition_reports",
                        to="logistics.deliveryorder",
                    ),
                ),
                (
                    "driver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="condition_reports",
                        to="logistics.driver",
                    ),
                ),
                (
                    "vehicle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="condition_reports",
                        to="logistics.vehicle",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
