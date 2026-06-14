"""Django admin for production module."""

from django.contrib import admin

from apps.production.models import (
    BillOfMaterials,
    BOMItem,
    Machine,
    OutputRecord,
    Product,
    WorkOrder,
)


class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "item", "standard_output", "is_active"]
    search_fields = ["name", "item__code"]


@admin.register(BillOfMaterials)
class BOMAdmin(admin.ModelAdmin):
    list_display = ["product", "version", "status", "material_cost_per_unit"]
    list_filter = ["status"]
    inlines = [BOMItemInline]


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ["wo_number", "product", "status", "shift", "quantity_planned"]
    list_filter = ["status", "shift"]
    search_fields = ["wo_number"]


@admin.register(OutputRecord)
class OutputRecordAdmin(admin.ModelAdmin):
    list_display = ["batch_number", "work_order", "date", "quantity_produced"]
    search_fields = ["batch_number"]


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ["machine_code", "name", "machine_type", "status"]
    search_fields = ["machine_code", "name"]
