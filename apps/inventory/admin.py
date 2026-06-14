from django.contrib import admin

from apps.inventory.models import (
    Item,
    ItemCategory,
    ItemSerialNumber,
    Stock,
    StockAdjustment,
    StockAlert,
    StockMovement,
    Warehouse,
)


@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "item_type",
        "unit_of_measure",
        "reorder_level",
        "is_active",
    )
    list_filter = ("item_type", "is_active", "category", "has_serial_number")
    search_fields = ("code", "name")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "manager", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "location")


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "warehouse",
        "quantity_on_hand",
        "quantity_reserved",
        "quantity_available",
        "last_updated",
    )
    list_filter = ("warehouse",)
    search_fields = ("item__code", "item__name")
    readonly_fields = ("quantity_available", "last_updated")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "warehouse",
        "movement_type",
        "quantity",
        "reference_type",
        "reference_id",
        "created_by",
        "created_at",
    )
    list_filter = ("movement_type", "reference_type", "warehouse")
    search_fields = ("item__code", "reference_id", "serial_number")
    readonly_fields = (
        "item",
        "warehouse",
        "movement_type",
        "reference_type",
        "reference_id",
        "quantity",
        "unit_cost",
        "serial_number",
        "expiry_date",
        "notes",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "item",
        "warehouse",
        "adjustment_type",
        "quantity",
        "status",
        "requested_by",
        "approved_by",
        "created_at",
    )
    list_filter = ("status", "adjustment_type", "warehouse")
    search_fields = ("item__code", "reason")
    readonly_fields = ("approved_by", "approved_at", "created_at", "updated_at")


@admin.register(ItemSerialNumber)
class ItemSerialNumberAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "item", "warehouse", "status", "sold_to", "is_active")
    list_filter = ("status", "warehouse", "is_active")
    search_fields = ("serial_number", "item__code")


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ("item", "warehouse", "alert_type", "is_read", "created_at")
    list_filter = ("alert_type", "is_read", "warehouse")
    search_fields = ("item__code", "message")
    readonly_fields = ("item", "warehouse", "alert_type", "message", "created_at")
