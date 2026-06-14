"""Serializers for the logistics module."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.logistics.models import (
    DeliveryNote,
    DeliveryOrder,
    DeliveryOrderItem,
    Driver,
    FuelRecord,
    Vehicle,
    VehicleMaintenance,
)
from apps.logistics.services import LogisticsService
from apps.logistics.utils import generate_document_number
from apps.hr.models import Employee
from apps.hr.services import HRService
from apps.users.models import User
class VehicleSerializer(serializers.ModelSerializer):
    total_trips = serializers.SerializerMethodField()
    total_km = serializers.SerializerMethodField()
    fuel_this_month = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "registration_number",
            "make",
            "model",
            "year",
            "vehicle_type",
            "capacity_kg",
            "color",
            "status",
            "insurance_expiry",
            "road_licence_expiry",
            "last_service_date",
            "next_service_date",
            "odometer_reading",
            "current_location",
            "is_active",
            "total_trips",
            "total_km",
            "fuel_this_month",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def _stats(self, obj):
        if not hasattr(obj, "_cached_stats"):
            obj._cached_stats = LogisticsService.vehicle_stats(obj)
        return obj._cached_stats

    def get_total_trips(self, obj):
        return self._stats(obj)["total_trips"]

    def get_total_km(self, obj):
        return self._stats(obj)["total_km"]

    def get_fuel_this_month(self, obj):
        return self._stats(obj)["fuel_this_month"]


class DriverSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    employee_id = serializers.SerializerMethodField()
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
    )
    employee = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.filter(status=Employee.STATUS_ACTIVE, is_active=True),
        write_only=True,
        required=False,
    )
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    total_trips = serializers.SerializerMethodField()
    on_time_percent = serializers.SerializerMethodField()
    incidents_count = serializers.IntegerField(read_only=True)
    current_assignment = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id",
            "user",
            "user_id",
            "employee",
            "employee_id",
            "full_name",
            "phone",
            "license_number",
            "license_class",
            "license_expiry",
            "medical_expiry",
            "employee_number",
            "availability_status",
            "assigned_vehicle",
            "is_available",
            "total_trips",
            "on_time_percent",
            "incidents_count",
            "current_assignment",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_employee_id(self, obj):
        profile = getattr(obj.user, "employee_profile", None)
        return profile.id if profile else None

    def validate(self, attrs):
        if self.instance:
            return attrs
        user = attrs.get("user")
        employee = attrs.get("employee")
        if not user and not employee:
            raise serializers.ValidationError(
                {"employee": "Select an active HR employee to register as a driver."}
            )
        if employee:
            if Driver.objects.filter(user_id=employee.user_id).exists() if employee.user_id else False:
                raise serializers.ValidationError({"employee": "This employee is already a driver."})
            if employee.user and getattr(employee.user, "driver_profile", None):
                raise serializers.ValidationError({"employee": "This employee is already a driver."})
        return attrs

    def create(self, validated_data):
        employee = validated_data.pop("employee", None)
        if employee and not validated_data.get("user"):
            user = HRService.ensure_user_for_employee(employee, role_name="Driver")
            validated_data["user"] = user
            validated_data.setdefault("employee_number", employee.employee_number)
        return super().create(validated_data)

    def get_total_trips(self, obj):
        return LogisticsService.driver_stats(obj)["total_trips"]

    def get_on_time_percent(self, obj):
        return LogisticsService.driver_stats(obj)["on_time_percent"]

    def get_current_assignment(self, obj):
        trip = (
            DeliveryOrder.objects.filter(
                driver=obj,
                status=DeliveryOrder.STATUS_IN_TRANSIT,
                is_active=True,
            )
            .values("do_number", "destination")
            .first()
        )
        return trip


class DeliveryItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    so_item_id = serializers.IntegerField(source="so_item.id", read_only=True)
    quantity_ordered = serializers.DecimalField(
        source="so_item.quantity_ordered",
        max_digits=18,
        decimal_places=4,
        read_only=True,
    )
    quantity_delivered = serializers.DecimalField(
        source="so_item.quantity_delivered",
        max_digits=18,
        decimal_places=4,
        read_only=True,
    )

    class Meta:
        model = DeliveryOrderItem
        fields = [
            "id",
            "so_item",
            "so_item_id",
            "item",
            "item_id",
            "item_code",
            "item_name",
            "quantity_ordered",
            "quantity_delivered",
            "quantity",
            "serial_number",
            "condition_out",
            "condition_in",
            "notes",
        ]
        read_only_fields = ["id"]


class DeliveryOrderSerializer(serializers.ModelSerializer):
    so_id = serializers.IntegerField(source="sales_order.id", read_only=True)
    so_number = serializers.CharField(source="sales_order.so_number", read_only=True)
    vehicle_id = serializers.IntegerField(source="vehicle.id", read_only=True, allow_null=True)
    vehicle_registration = serializers.CharField(
        source="vehicle.registration_number", read_only=True, allow_null=True
    )
    driver_id = serializers.IntegerField(source="driver.id", read_only=True, allow_null=True)
    driver_name = serializers.SerializerMethodField()
    driver_phone = serializers.SerializerMethodField()
    origin_warehouse_id = serializers.IntegerField(source="origin_warehouse.id", read_only=True)
    origin_warehouse_name = serializers.CharField(source="origin_warehouse.name", read_only=True)
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    items = DeliveryItemSerializer(many=True)

    class Meta:
        model = DeliveryOrder
        fields = [
            "id",
            "do_number",
            "sales_order",
            "so_id",
            "so_number",
            "vehicle",
            "vehicle_id",
            "vehicle_registration",
            "driver",
            "driver_id",
            "driver_name",
            "driver_phone",
            "origin_warehouse",
            "origin_warehouse_id",
            "origin_warehouse_name",
            "destination",
            "customer",
            "customer_id",
            "customer_name",
            "scheduled_date",
            "actual_departure",
            "actual_arrival",
            "distance_km",
            "status",
            "trip_status",
            "logistics_review_status",
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
            "failure_reason",
            "notes",
            "items",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "do_number",
            "status",
            "actual_departure",
            "actual_arrival",
            "failure_reason",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_driver_name(self, obj):
        return obj.driver.user.get_full_name() if obj.driver else ""

    def get_driver_phone(self, obj):
        return obj.driver.user.phone if obj.driver else ""

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["do_number"] = generate_document_number("DO", DeliveryOrder, "do_number")
        validated_data["created_by"] = self.context["request"].user
        so = validated_data["sales_order"]
        validated_data.setdefault("customer", so.customer)
        validated_data.setdefault("destination", so.delivery_address)
        order = DeliveryOrder.objects.create(**validated_data)
        for item_data in items_data:
            DeliveryOrderItem.objects.create(delivery_order=order, **item_data)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != DeliveryOrder.STATUS_SCHEDULED:
            raise serializers.ValidationError("Only scheduled delivery orders can be edited.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                DeliveryOrderItem.objects.create(delivery_order=instance, **item_data)
        return instance


class DeliveryNoteSerializer(serializers.ModelSerializer):
    do_id = serializers.IntegerField(source="delivery_order.id", read_only=True)
    do_number = serializers.CharField(source="delivery_order.do_number", read_only=True)
    customer_name = serializers.CharField(
        source="delivery_order.customer.name", read_only=True
    )
    delivery_date = serializers.DateTimeField(
        source="delivery_order.actual_arrival", read_only=True, allow_null=True
    )

    class Meta:
        model = DeliveryNote
        fields = [
            "id",
            "dn_number",
            "delivery_order",
            "do_id",
            "do_number",
            "customer_name",
            "delivery_date",
            "signed_by",
            "signed_at",
            "customer_feedback",
            "condition_notes",
            "status",
            "created_at",
        ]
        read_only_fields = ["dn_number", "status", "created_at"]


class MaintenanceSerializer(serializers.ModelSerializer):
    vehicle_id = serializers.IntegerField(source="vehicle.id", read_only=True)
    vehicle_registration = serializers.CharField(
        source="vehicle.registration_number", read_only=True
    )
    vehicle_make_model = serializers.SerializerMethodField()

    class Meta:
        model = VehicleMaintenance
        fields = [
            "id",
            "vehicle",
            "vehicle_id",
            "vehicle_registration",
            "vehicle_make_model",
            "maintenance_type",
            "description",
            "cost",
            "service_date",
            "next_service_date",
            "performed_by",
            "status",
            "work_done",
            "parts_replaced",
            "odometer_reading",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_vehicle_make_model(self, obj):
        return f"{obj.vehicle.make} {obj.vehicle.model}"


class FuelRecordSerializer(serializers.ModelSerializer):
    vehicle_id = serializers.IntegerField(source="vehicle.id", read_only=True)
    vehicle_registration = serializers.CharField(
        source="vehicle.registration_number", read_only=True
    )
    driver_id = serializers.IntegerField(source="driver.id", read_only=True, allow_null=True)
    driver_name = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="recorded_by.get_full_name", read_only=True)

    class Meta:
        model = FuelRecord
        fields = [
            "id",
            "vehicle",
            "vehicle_id",
            "vehicle_registration",
            "driver",
            "driver_id",
            "driver_name",
            "date",
            "liters",
            "cost_per_liter",
            "total_cost",
            "odometer_reading",
            "station_name",
            "notes",
            "recorded_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["recorded_by", "created_at"]

    def get_driver_name(self, obj):
        return obj.driver.user.get_full_name() if obj.driver else ""

    def create(self, validated_data):
        validated_data["recorded_by"] = self.context["request"].user
        liters = validated_data["liters"]
        cost = validated_data["cost_per_liter"]
        validated_data["total_cost"] = (liters * cost).quantize(Decimal("0.01"))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        liters = validated_data.get("liters", instance.liters)
        cost = validated_data.get("cost_per_liter", instance.cost_per_liter)
        validated_data["total_cost"] = (liters * cost).quantize(Decimal("0.01"))
        return super().update(instance, validated_data)


class DeliveredSerializer(serializers.Serializer):
    signed_by = serializers.CharField(required=True)
    customer_feedback = serializers.CharField(required=False, allow_blank=True)
    condition_notes = serializers.CharField(required=False, allow_blank=True)
    actual_arrival = serializers.DateTimeField(required=False)


class FailedSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True)


class CompleteMaintenanceSerializer(serializers.Serializer):
    service_date = serializers.DateField(required=True)
    cost = serializers.DecimalField(max_digits=18, decimal_places=2)
    next_service_date = serializers.DateField(required=False, allow_null=True)
    work_done = serializers.CharField(required=False, allow_blank=True)
    parts_replaced = serializers.CharField(required=False, allow_blank=True)
    odometer_reading = serializers.IntegerField(required=False, allow_null=True)


class SignDeliveryNoteSerializer(serializers.Serializer):
    signed_by = serializers.CharField(required=True)
    customer_feedback = serializers.CharField(required=False, allow_blank=True)
    condition_notes = serializers.CharField(required=False, allow_blank=True)


class SalesOrderLogisticsSerializer(serializers.ModelSerializer):
    """Sales order summary for logistics workflow queues."""

    customer_name = serializers.CharField(source="customer.name", read_only=True)
    delivery_cost_detail = serializers.SerializerMethodField()
    delivery_order_id = serializers.SerializerMethodField()

    class Meta:
        from apps.sales.models import SalesOrder

        model = SalesOrder
        fields = [
            "id",
            "so_number",
            "status",
            "customer_name",
            "delivery_address",
            "requested_delivery_location",
            "delivery_method",
            "delivery_cost",
            "subtotal",
            "total_amount",
            "delivery_date",
            "delivery_cost_detail",
            "delivery_order_id",
            "created_at",
            "updated_at",
        ]

    def get_delivery_cost_detail(self, obj):
        detail = getattr(obj, "delivery_cost_detail", None)
        if not detail:
            return None
        return {
            "delivery_distance_km": str(detail.delivery_distance_km),
            "transport_method": detail.transport_method,
            "vehicle_type": detail.vehicle_type,
            "fuel_cost": str(detail.fuel_cost),
            "loading_cost": str(detail.loading_cost),
            "offloading_cost": str(detail.offloading_cost),
            "additional_charges": str(detail.additional_charges),
            "total_delivery_cost": str(detail.total_delivery_cost),
            "notes": detail.notes,
        }

    def get_delivery_order_id(self, obj):
        delivery = obj.delivery_orders.filter(is_active=True).order_by("-created_at").first()
        return delivery.id if delivery else None


class SalesOrderLogisticsDetailSerializer(SalesOrderLogisticsSerializer):
    """Full sales order detail for logistics in-transit / dispatch views."""

    from apps.sales.serializers import SOItemSerializer
    from apps.sales.workflow_serializers import DispatchAssignmentSerializer

    items = SOItemSerializer(many=True, read_only=True)
    dispatch_assignment = DispatchAssignmentSerializer(read_only=True)
    delivery_order = serializers.SerializerMethodField()
    customer_address = serializers.CharField(source="customer.address", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    customer_contact = serializers.CharField(source="customer.contact_person", read_only=True)
    warehouse_name = serializers.CharField(
        source="fulfillment_warehouse.name", read_only=True, allow_null=True
    )
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)

    class Meta(SalesOrderLogisticsSerializer.Meta):
        fields = SalesOrderLogisticsSerializer.Meta.fields + [
            "items",
            "dispatch_assignment",
            "delivery_order",
            "customer_address",
            "customer_phone",
            "customer_email",
            "customer_contact",
            "warehouse_name",
            "currency_code",
            "inventory_status",
            "delivery_status",
            "payment_status",
            "lpo_number",
            "tax_amount",
            "discount_amount",
            "notes",
            "created_by_name",
        ]

    def get_delivery_order(self, obj):
        delivery = (
            obj.delivery_orders.filter(is_active=True)
            .select_related("vehicle", "driver__user", "origin_warehouse")
            .order_by("-created_at")
            .first()
        )
        if not delivery:
            return None
        driver = delivery.driver
        vehicle = delivery.vehicle
        return {
            "id": delivery.id,
            "do_number": delivery.do_number,
            "status": delivery.status,
            "destination": delivery.destination,
            "origin_warehouse_name": delivery.origin_warehouse.name,
            "scheduled_date": delivery.scheduled_date,
            "actual_departure": delivery.actual_departure,
            "actual_arrival": delivery.actual_arrival,
            "distance_km": str(delivery.distance_km),
            "notes": delivery.notes,
            "vehicle_registration": vehicle.registration_number if vehicle else None,
            "vehicle_make": vehicle.make if vehicle else None,
            "vehicle_model": vehicle.model if vehicle else None,
            "vehicle_type": vehicle.vehicle_type if vehicle else None,
            "vehicle_status": vehicle.status if vehicle else None,
            "driver_name": driver.user.get_full_name() if driver else None,
            "driver_phone": getattr(
                getattr(obj, "dispatch_assignment", None), "driver_phone", None
            )
            or (driver.user.phone if driver and hasattr(driver.user, "phone") else None),
            "driver_license": driver.license_number if driver else None,
        }
