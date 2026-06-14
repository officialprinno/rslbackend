"""Serializers for the inventory module."""

from django.utils import timezone
from rest_framework import serializers

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
from apps.inventory.services import InsufficientStockError, StockService


class ItemCategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = ItemCategory
        fields = [
            "id",
            "code",
            "name",
            "description",
            "parent",
            "parent_name",
            "children_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_children_count(self, obj):
        return obj.children.filter(is_active=True).count()

    def validate_code(self, value):
        return value.strip().upper() if value else value

    def validate(self, attrs):
        parent = attrs.get("parent") or getattr(self.instance, "parent", None)
        if parent and self.instance and parent.pk == self.instance.pk:
            raise serializers.ValidationError({"parent": "A category cannot be its own parent."})
        return attrs


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = Item
        fields = [
            "id",
            "code",
            "name",
            "subcategory",
            "description",
            "category",
            "category_name",
            "item_type",
            "item_usage",
            "unit_of_measure",
            "has_serial_number",
            "has_batch_tracking",
            "has_expiry_date",
            "reorder_level",
            "minimum_stock",
            "maximum_stock",
            "safety_stock",
            "lead_time_days",
            "preferred_supplier",
            "currency",
            "currency_code",
            "unit_cost",
            "selling_price",
            "is_active",
            "tracks_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "tracks_stock"]

    tracks_stock = serializers.BooleanField(read_only=True)

    def validate_code(self, value):
        return value.strip().upper()


class WarehouseSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source="manager.get_full_name", read_only=True)

    class Meta:
        model = Warehouse
        fields = [
            "id",
            "name",
            "location",
            "warehouse_type",
            "capacity",
            "manager",
            "manager_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class StockSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    unit_of_measure = serializers.CharField(source="item.unit_of_measure", read_only=True)
    reorder_level = serializers.DecimalField(
        source="item.reorder_level",
        max_digits=18,
        decimal_places=4,
        read_only=True,
    )
    unit_cost = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "warehouse",
            "warehouse_name",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "unit_of_measure",
            "reorder_level",
            "unit_cost",
            "total_value",
            "status",
            "last_updated",
        ]
        read_only_fields = [
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "unit_cost",
            "total_value",
            "status",
            "last_updated",
        ]

    def get_unit_cost(self, obj):
        return obj.item.unit_cost

    def get_total_value(self, obj):
        return obj.quantity_on_hand * obj.item.unit_cost

    def get_status(self, obj):
        qty = obj.quantity_available
        reorder = obj.item.reorder_level
        if qty <= 0:
            return "OUT_OF_STOCK"
        if qty <= reorder:
            return "LOW_STOCK"
        return "IN_STOCK"


class StockSummarySerializer(serializers.Serializer):
    total_items = serializers.IntegerField()
    low_stock_count = serializers.IntegerField()
    out_of_stock_count = serializers.IntegerField()
    total_stock_value = serializers.DecimalField(max_digits=18, decimal_places=2)


class StockMovementSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "warehouse",
            "warehouse_name",
            "movement_type",
            "reference_type",
            "reference_id",
            "quantity",
            "unit_cost",
            "serial_number",
            "expiry_date",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]

    def validate(self, attrs):
        item = attrs.get("item") or self.instance.item
        if attrs.get("serial_number") and not item.has_serial_number:
            raise serializers.ValidationError(
                {"serial_number": "This item does not track serial numbers."}
            )
        if attrs.get("expiry_date") and not item.has_expiry_date:
            raise serializers.ValidationError(
                {"expiry_date": "This item does not track expiry dates."}
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request else None
        movement_type = validated_data["movement_type"]
        quantity = validated_data["quantity"]

        try:
            stock, movement = StockService.record_movement(
                item=validated_data["item"],
                warehouse=validated_data["warehouse"],
                movement_type=movement_type,
                quantity=quantity,
                reference_type=validated_data.get(
                    "reference_type", StockMovement.REFERENCE_MANUAL
                ),
                reference_id=validated_data.get("reference_id", ""),
                unit_cost=validated_data.get("unit_cost"),
                serial_number=validated_data.get("serial_number", ""),
                expiry_date=validated_data.get("expiry_date"),
                notes=validated_data.get("notes", ""),
                created_by=user,
            )
        except InsufficientStockError as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            raise serializers.ValidationError({"quantity": detail}) from exc

        return movement


class StockAdjustmentSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.get_full_name",
        read_only=True,
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name",
        read_only=True,
    )

    class Meta:
        model = StockAdjustment
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "warehouse",
            "warehouse_name",
            "adjustment_type",
            "quantity",
            "reason",
            "status",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["requested_by"] = request.user
        validated_data["status"] = StockAdjustment.STATUS_PENDING
        return super().create(validated_data)


class StockAdjustmentApproveSerializer(serializers.Serializer):
    """Empty body — approval uses the authenticated user."""

    def save(self, adjustment, user):
        if adjustment.status != StockAdjustment.STATUS_PENDING:
            raise serializers.ValidationError("Only pending adjustments can be approved.")

        from apps.inventory.store_permissions import can_approve_adjustment

        allowed, reason = can_approve_adjustment(user, adjustment)
        if not allowed:
            raise serializers.ValidationError(reason)

        adjustment.status = StockAdjustment.STATUS_APPROVED
        adjustment.approved_by = user
        adjustment.approved_at = timezone.now()
        adjustment.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        try:
            StockService.apply_adjustment(adjustment, approved_by=user)
        except InsufficientStockError as exc:
            adjustment.status = StockAdjustment.STATUS_PENDING
            adjustment.approved_by = None
            adjustment.approved_at = None
            adjustment.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            raise serializers.ValidationError({"quantity": detail}) from exc
        return adjustment


class ItemSerialNumberSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    sold_to_name = serializers.CharField(source="sold_to.name", read_only=True)

    class Meta:
        model = ItemSerialNumber
        fields = [
            "id",
            "item",
            "item_code",
            "warehouse",
            "warehouse_name",
            "serial_number",
            "manufacturer_serial",
            "purchase_date",
            "warranty_date",
            "status",
            "sold_to",
            "sold_to_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        item = attrs.get("item") or getattr(self.instance, "item", None)
        if item and not item.has_serial_number:
            raise serializers.ValidationError(
                {"item": "This item does not require serial number tracking."}
            )
        return attrs


class StockAlertSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StockAlert
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "warehouse",
            "warehouse_name",
            "alert_type",
            "message",
            "is_read",
            "created_at",
        ]
        read_only_fields = ["alert_type", "message", "created_at"]
