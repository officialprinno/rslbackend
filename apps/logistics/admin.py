"""Django admin for logistics module."""

from django.contrib import admin

from apps.logistics.models import (
    DeliveryNote,
    DeliveryOrder,
    Driver,
    FuelRecord,
    Vehicle,
    VehicleMaintenance,
)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["registration_number", "make", "model", "vehicle_type", "status", "is_active"]
    search_fields = ["registration_number", "make", "model"]
    list_filter = ["vehicle_type", "status"]


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ["user", "license_number", "license_class", "is_available", "is_active"]
    search_fields = ["license_number", "user__email"]


@admin.register(DeliveryOrder)
class DeliveryOrderAdmin(admin.ModelAdmin):
    list_display = ["do_number", "customer", "status", "scheduled_date", "vehicle", "driver"]
    search_fields = ["do_number"]
    list_filter = ["status"]


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = ["dn_number", "delivery_order", "status", "signed_at"]
    search_fields = ["dn_number"]


@admin.register(VehicleMaintenance)
class VehicleMaintenanceAdmin(admin.ModelAdmin):
    list_display = ["vehicle", "maintenance_type", "service_date", "status", "cost"]
    list_filter = ["maintenance_type", "status"]


@admin.register(FuelRecord)
class FuelRecordAdmin(admin.ModelAdmin):
    list_display = ["vehicle", "date", "liters", "total_cost", "station_name"]
    search_fields = ["vehicle__registration_number"]
