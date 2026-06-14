"""Serializers for the driver portal API."""

from rest_framework import serializers

from apps.logistics.models import (
    DeliveryConfirmation,
    DeliveryOrder,
    DeliveryOrderItem,
    DeliveryTripEvent,
    Driver,
    Vehicle,
    VehicleConditionReport,
)
from apps.logistics.services import LogisticsService


class DriverProfileSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    department = serializers.SerializerMethodField()
    assigned_vehicle_registration = serializers.CharField(
        source="assigned_vehicle.registration_number",
        read_only=True,
        allow_null=True,
    )
    assigned_vehicle_id = serializers.IntegerField(
        source="assigned_vehicle.id",
        read_only=True,
        allow_null=True,
    )
    performance = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id",
            "user_id",
            "employee_number",
            "full_name",
            "phone",
            "email",
            "license_number",
            "license_class",
            "license_expiry",
            "medical_expiry",
            "department",
            "assigned_vehicle_id",
            "assigned_vehicle_registration",
            "availability_status",
            "is_available",
            "is_active",
            "performance",
            "created_at",
        ]

    def get_department(self, obj):
        role = getattr(obj.user, "role", None)
        if role and role.department:
            return role.department.name
        return "Logistics"

    def get_performance(self, obj):
        from apps.logistics.driver_portal_service import DriverPortalService

        return DriverPortalService.driver_performance(obj)


class DriverTripItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = DeliveryOrderItem
        fields = [
            "id",
            "item_id",
            "item_code",
            "item_name",
            "quantity",
            "serial_number",
            "condition_out",
        ]


class DeliveryConfirmationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryConfirmation
        fields = [
            "receiver_name",
            "receiver_position",
            "receiver_phone",
            "receiver_company",
            "quantity_delivered",
            "delivery_notes",
            "signature_data",
            "proof_photo_url",
            "proof_document_url",
            "confirmed_at",
        ]


class TripEventSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = DeliveryTripEvent
        fields = [
            "id",
            "action",
            "from_status",
            "to_status",
            "details",
            "user_name",
            "created_at",
        ]


class DriverTripSerializer(serializers.ModelSerializer):
    so_number = serializers.CharField(source="sales_order.so_number", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    vehicle_registration = serializers.CharField(
        source="vehicle.registration_number",
        read_only=True,
        allow_null=True,
    )
    origin_warehouse_name = serializers.CharField(
        source="origin_warehouse.name",
        read_only=True,
    )
    items = DriverTripItemSerializer(many=True, read_only=True)
    confirmation = DeliveryConfirmationSerializer(read_only=True)
    trip_events = TripEventSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryOrder
        fields = [
            "id",
            "do_number",
            "so_number",
            "customer_name",
            "destination",
            "origin_warehouse_name",
            "vehicle_registration",
            "scheduled_date",
            "status",
            "trip_status",
            "logistics_review_status",
            "distance_km",
            "odometer_start",
            "odometer_end",
            "fuel_remaining",
            "vehicle_condition_start",
            "vehicle_condition_end",
            "trip_started_at",
            "arrived_at",
            "delivered_at",
            "return_started_at",
            "return_confirmed_at",
            "notes",
            "items",
            "confirmation",
            "trip_events",
            "created_at",
        ]


class StartDeliverySerializer(serializers.Serializer):
    odometer_start = serializers.IntegerField(min_value=0)
    vehicle_condition = serializers.CharField(max_length=50, default="GOOD")


class ArrivalSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ConfirmDeliverySerializer(serializers.Serializer):
    receiver_name = serializers.CharField(max_length=150)
    receiver_position = serializers.CharField(required=False, allow_blank=True, default="")
    receiver_phone = serializers.CharField(required=False, allow_blank=True, default="")
    receiver_company = serializers.CharField(required=False, allow_blank=True, default="")
    quantity_delivered = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    delivery_notes = serializers.CharField(required=False, allow_blank=True, default="")
    signature_data = serializers.CharField(required=False, allow_blank=True, default="")
    proof_photo_url = serializers.URLField(required=False, allow_blank=True, default="")
    proof_document_url = serializers.URLField(required=False, allow_blank=True, default="")


class StartReturnSerializer(serializers.Serializer):
    vehicle_condition = serializers.CharField(max_length=50, default="GOOD")


class ConfirmReturnSerializer(serializers.Serializer):
    odometer_end = serializers.IntegerField(min_value=0)
    fuel_remaining = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    vehicle_condition = serializers.CharField(max_length=50, default="GOOD")


class VehicleConditionSerializer(serializers.Serializer):
    vehicle = serializers.IntegerField()
    delivery_order = serializers.IntegerField(required=False, allow_null=True)
    condition = serializers.ChoiceField(choices=VehicleConditionReport.CONDITION_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    odometer_reading = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    fuel_remaining = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    photo_url = serializers.URLField(required=False, allow_blank=True, default="")


class DriverDashboardSerializer(serializers.Serializer):
    assigned_count = serializers.IntegerField()
    in_progress_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    availability_status = serializers.CharField()
    active_trip_id = serializers.IntegerField(allow_null=True)
    current_vehicle = serializers.SerializerMethodField()

    def get_current_vehicle(self, obj):
        vehicle = obj.get("current_vehicle")
        if not vehicle:
            return None
        return {
            "id": vehicle.id,
            "registration_number": vehicle.registration_number,
            "make": vehicle.make,
            "model": vehicle.model,
            "status": vehicle.status,
            "odometer_reading": vehicle.odometer_reading,
        }


class LogisticsReviewSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
