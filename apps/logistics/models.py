"""
Logistics models for Rock Solutions FMS.

Vehicles → Drivers → Delivery Orders → Delivery Notes
Maintenance & Fuel tracking
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Vehicle(BaseModel):
    """Company fleet vehicle."""

    TYPE_TRUCK = "TRUCK"
    TYPE_PICKUP = "PICKUP"
    TYPE_VAN = "VAN"
    TYPE_TANKER = "TANKER"
    TYPE_OTHER = "OTHER"
    TYPE_CHOICES = [
        (TYPE_TRUCK, "Truck"),
        (TYPE_PICKUP, "Pickup"),
        (TYPE_VAN, "Van"),
        (TYPE_TANKER, "Tanker"),
        (TYPE_OTHER, "Other"),
    ]

    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_ON_TRIP = "ON_TRIP"
    STATUS_IN_USE = "IN_USE"
    STATUS_RETURNING = "RETURNING"
    STATUS_MAINTENANCE = "MAINTENANCE"
    STATUS_BREAKDOWN = "BREAKDOWN"
    STATUS_OUT_OF_SERVICE = "OUT_OF_SERVICE"
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_ON_TRIP, "On Trip"),
        (STATUS_IN_USE, "In Use"),
        (STATUS_RETURNING, "Returning"),
        (STATUS_MAINTENANCE, "Maintenance"),
        (STATUS_BREAKDOWN, "Breakdown"),
        (STATUS_OUT_OF_SERVICE, "Out of Service"),
    ]

    registration_number = models.CharField(max_length=30, unique=True)
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    vehicle_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TRUCK)
    capacity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    color = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
    )
    insurance_expiry = models.DateField(null=True, blank=True)
    road_licence_expiry = models.DateField(null=True, blank=True)
    last_service_date = models.DateField(null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)
    odometer_reading = models.PositiveIntegerField(default=0)
    current_location = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["registration_number"]

    def __str__(self):
        return self.registration_number


class Driver(BaseModel):
    """Fleet driver — linked to system user (HR employee when available)."""

    CLASS_B = "B"
    CLASS_C = "C"
    CLASS_CE = "CE"
    CLASS_D = "D"
    LICENSE_CLASS_CHOICES = [
        (CLASS_B, "Class B"),
        (CLASS_C, "Class C"),
        (CLASS_CE, "Class CE"),
        (CLASS_D, "Class D"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="driver_profile",
    )
    license_number = models.CharField(max_length=50, unique=True)
    license_class = models.CharField(max_length=5, choices=LICENSE_CLASS_CHOICES)
    AVAIL_AVAILABLE = "AVAILABLE"
    AVAIL_ON_DELIVERY = "ON_DELIVERY"
    AVAIL_RETURNING = "RETURNING"
    AVAIL_OFF_DUTY = "OFF_DUTY"
    AVAILABILITY_CHOICES = [
        (AVAIL_AVAILABLE, "Available"),
        (AVAIL_ON_DELIVERY, "On Delivery"),
        (AVAIL_RETURNING, "Returning"),
        (AVAIL_OFF_DUTY, "Off Duty"),
    ]

    employee_number = models.CharField(max_length=50, blank=True)
    license_expiry = models.DateField()
    medical_expiry = models.DateField()
    is_available = models.BooleanField(default=True)
    availability_status = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default=AVAIL_AVAILABLE,
    )
    assigned_vehicle = models.ForeignKey(
        "Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_drivers",
    )
    incidents_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.user.get_full_name()


class DeliveryOrder(BaseModel):
    """Delivery / shipment order."""

    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_IN_TRANSIT = "IN_TRANSIT"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_IN_TRANSIT, "In Transit"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    TRIP_ASSIGNED = "ASSIGNED"
    TRIP_STARTED = "STARTED"
    TRIP_IN_TRANSIT = "IN_TRANSIT"
    TRIP_ARRIVED = "ARRIVED"
    TRIP_DELIVERED = "DELIVERED"
    TRIP_RETURNING = "RETURNING"
    TRIP_RETURN_CONFIRMED = "RETURN_CONFIRMED"
    TRIP_CHOICES = [
        (TRIP_ASSIGNED, "Assigned"),
        (TRIP_STARTED, "Started"),
        (TRIP_IN_TRANSIT, "In Transit"),
        (TRIP_ARRIVED, "Arrived"),
        (TRIP_DELIVERED, "Delivered"),
        (TRIP_RETURNING, "Returning"),
        (TRIP_RETURN_CONFIRMED, "Return Confirmed"),
    ]

    REVIEW_PENDING = "PENDING"
    REVIEW_APPROVED = "APPROVED"
    REVIEW_REJECTED = "REJECTED"
    REVIEW_CHOICES = [
        (REVIEW_PENDING, "Pending Review"),
        (REVIEW_APPROVED, "Approved"),
        (REVIEW_REJECTED, "Rejected"),
    ]

    do_number = models.CharField(max_length=30, unique=True, editable=False)
    sales_order = models.ForeignKey(
        "sales.SalesOrder",
        on_delete=models.PROTECT,
        related_name="delivery_orders",
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="delivery_orders",
        null=True,
        blank=True,
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.PROTECT,
        related_name="delivery_orders",
        null=True,
        blank=True,
    )
    origin_warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.PROTECT,
        related_name="delivery_orders",
    )
    destination = models.TextField()
    customer = models.ForeignKey(
        "sales.Customer",
        on_delete=models.PROTECT,
        related_name="delivery_orders",
    )
    scheduled_date = models.DateTimeField()
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
    )
    trip_status = models.CharField(
        max_length=20,
        choices=TRIP_CHOICES,
        default=TRIP_ASSIGNED,
    )
    logistics_review_status = models.CharField(
        max_length=20,
        choices=REVIEW_CHOICES,
        default=REVIEW_PENDING,
    )
    odometer_start = models.PositiveIntegerField(null=True, blank=True)
    odometer_end = models.PositiveIntegerField(null=True, blank=True)
    fuel_remaining = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    vehicle_condition_start = models.CharField(max_length=50, blank=True)
    vehicle_condition_end = models.CharField(max_length=50, blank=True)
    trip_started_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    return_started_at = models.DateTimeField(null=True, blank=True)
    return_confirmed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivery_orders_created",
    )

    class Meta:
        ordering = ["-scheduled_date"]

    def __str__(self):
        return self.do_number


class DeliveryOrderItem(models.Model):
    """Line item on a delivery order."""

    delivery_order = models.ForeignKey(
        DeliveryOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    so_item = models.ForeignKey(
        "sales.SalesOrderItem",
        on_delete=models.PROTECT,
        related_name="logistics_delivery_lines",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="logistics_delivery_lines",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    serial_number = models.CharField(max_length=100, blank=True)
    condition_out = models.CharField(max_length=100, default="Good")
    condition_in = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]


class DeliveryNote(BaseModel):
    """Proof of delivery record."""

    STATUS_PENDING = "PENDING"
    STATUS_SIGNED = "SIGNED"
    STATUS_DISPUTED = "DISPUTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SIGNED, "Signed"),
        (STATUS_DISPUTED, "Disputed"),
    ]

    dn_number = models.CharField(max_length=30, unique=True, editable=False)
    delivery_order = models.OneToOneField(
        DeliveryOrder,
        on_delete=models.PROTECT,
        related_name="delivery_note",
    )
    signed_by = models.CharField(max_length=150, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    customer_feedback = models.TextField(blank=True)
    condition_notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.dn_number


class VehicleMaintenance(BaseModel):
    """Vehicle service / repair record."""

    TYPE_SERVICE = "SERVICE"
    TYPE_REPAIR = "REPAIR"
    TYPE_INSPECTION = "INSPECTION"
    TYPE_CHOICES = [
        (TYPE_SERVICE, "Service"),
        (TYPE_REPAIR, "Repair"),
        (TYPE_INSPECTION, "Inspection"),
    ]

    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
    ]

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="maintenance_records",
    )
    maintenance_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField()
    cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    service_date = models.DateField()
    next_service_date = models.DateField(null=True, blank=True)
    performed_by = models.CharField(max_length=150, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
    )
    work_done = models.TextField(blank=True)
    parts_replaced = models.TextField(blank=True)
    odometer_reading = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-service_date"]

    def __str__(self):
        return f"{self.vehicle.registration_number} — {self.maintenance_type}"


class FuelRecord(BaseModel):
    """Fuel consumption log."""

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fuel_records",
    )
    date = models.DateField()
    liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    cost_per_liter = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    total_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    odometer_reading = models.PositiveIntegerField(default=0)
    station_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="fuel_records_recorded",
    )

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.vehicle.registration_number} — {self.date}"


class DeliveryConfirmation(BaseModel):
    """Driver-submitted proof of delivery with receiver details."""

    delivery_order = models.OneToOneField(
        DeliveryOrder,
        on_delete=models.CASCADE,
        related_name="confirmation",
    )
    receiver_name = models.CharField(max_length=150)
    receiver_position = models.CharField(max_length=150, blank=True)
    receiver_phone = models.CharField(max_length=30, blank=True)
    receiver_company = models.CharField(max_length=255, blank=True)
    quantity_delivered = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    delivery_notes = models.TextField(blank=True)
    signature_data = models.TextField(blank=True)
    proof_photo_url = models.URLField(blank=True)
    proof_document_url = models.URLField(blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivery_confirmations",
    )
    confirmed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-confirmed_at"]

    def __str__(self):
        return f"Confirmation — {self.delivery_order.do_number}"


class DeliveryTripEvent(BaseModel):
    """Audit trail for driver trip status changes."""

    delivery_order = models.ForeignKey(
        DeliveryOrder,
        on_delete=models.CASCADE,
        related_name="trip_events",
    )
    action = models.CharField(max_length=80)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    details = models.TextField(blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="delivery_trip_events",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.delivery_order.do_number} — {self.action}"


class VehicleConditionReport(BaseModel):
    """Driver-reported vehicle condition during or after a trip."""

    COND_GOOD = "GOOD"
    COND_MINOR = "MINOR_ISSUE"
    COND_MAINTENANCE = "MAINTENANCE_REQUIRED"
    COND_BREAKDOWN = "BREAKDOWN"
    CONDITION_CHOICES = [
        (COND_GOOD, "Good"),
        (COND_MINOR, "Minor Issue"),
        (COND_MAINTENANCE, "Maintenance Required"),
        (COND_BREAKDOWN, "Breakdown"),
    ]

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="condition_reports",
    )
    driver = models.ForeignKey(
        Driver,
        on_delete=models.PROTECT,
        related_name="condition_reports",
    )
    delivery_order = models.ForeignKey(
        DeliveryOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="condition_reports",
    )
    condition = models.CharField(max_length=30, choices=CONDITION_CHOICES)
    notes = models.TextField(blank=True)
    odometer_reading = models.PositiveIntegerField(null=True, blank=True)
    fuel_remaining = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    photo_url = models.URLField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.vehicle.registration_number} — {self.condition}"
