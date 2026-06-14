"""Serializers for extended inventory features."""

from rest_framework import serializers

from apps.inventory.models import (
    DepartmentRequest,
    DepartmentRequestLine,
    GoodsIssueLine,
    GoodsIssueNote,
    StockBatch,
    StockMovement,
    StockTake,
    StockTakeLine,
    StockTransfer,
    StockTransferLine,
)
from apps.inventory.services import StockService
from apps.inventory.workflow import (
    approve_department_request,
    approve_goods_issue,
    approve_stock_take,
    approve_stock_transfer,
    complete_stock_transfer,
    create_dept_request_number,
    create_gin_number,
    create_stock_take_number,
    create_transfer_number,
    issue_department_request,
    reject_department_request,
    reject_goods_issue,
    reject_stock_take,
    reject_stock_transfer,
)


class StockBatchSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = StockBatch
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "warehouse",
            "warehouse_name",
            "batch_number",
            "manufacture_date",
            "expiry_date",
            "supplier",
            "supplier_name",
            "quantity",
            "unit_cost",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def create(self, validated_data):
        batch = super().create(validated_data)
        request = self.context.get("request")
        user = request.user if request else None
        StockService.record_movement(
            item=batch.item,
            warehouse=batch.warehouse,
            movement_type=StockMovement.MOVEMENT_IN,
            quantity=batch.quantity,
            reference_type=StockMovement.REFERENCE_MANUAL,
            reference_id=batch.batch_number,
            unit_cost=batch.unit_cost,
            expiry_date=batch.expiry_date,
            notes=f"Batch receipt: {batch.batch_number}",
            created_by=user,
        )
        return batch


class StockTransferLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = StockTransferLine
        fields = ["id", "item", "item_code", "item_name", "quantity"]


class StockTransferSerializer(serializers.ModelSerializer):
    source_warehouse_name = serializers.CharField(
        source="source_warehouse.name", read_only=True
    )
    destination_warehouse_name = serializers.CharField(
        source="destination_warehouse.name", read_only=True
    )
    requested_by_name = serializers.CharField(
        source="requested_by.get_full_name", read_only=True
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True
    )
    lines = StockTransferLineSerializer(many=True)

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "transfer_number",
            "source_warehouse",
            "source_warehouse_name",
            "destination_warehouse",
            "destination_warehouse_name",
            "status",
            "notes",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "transfer_number",
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        source = attrs.get("source_warehouse") or getattr(
            self.instance, "source_warehouse", None
        )
        dest = attrs.get("destination_warehouse") or getattr(
            self.instance, "destination_warehouse", None
        )
        if source and dest and source.pk == dest.pk:
            raise serializers.ValidationError(
                {"destination_warehouse": "Source and destination must differ."}
            )
        return attrs

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        request = self.context.get("request")
        transfer = StockTransfer.objects.create(
            transfer_number=create_transfer_number(),
            requested_by=request.user,
            **validated_data,
        )
        for line in lines_data:
            StockTransferLine.objects.create(transfer=transfer, **line)
        return transfer


class DepartmentRequestLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_usage = serializers.CharField(source="item.item_usage", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, allow_null=True)
    remaining_qty = serializers.SerializerMethodField()
    available_stock = serializers.SerializerMethodField()

    class Meta:
        model = DepartmentRequestLine
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "item_usage",
            "quantity",
            "requested_qty",
            "issued_qty",
            "remaining_qty",
            "available_stock",
            "warehouse",
            "warehouse_name",
            "notes",
        ]

    def get_remaining_qty(self, obj):
        requested = obj.requested_qty or obj.quantity
        return requested - (obj.issued_qty or 0)

    def get_available_stock(self, obj):
        from apps.inventory.models import Stock

        wh = obj.warehouse or obj.request.warehouse
        stock = Stock.objects.filter(item=obj.item, warehouse=wh).first()
        return stock.quantity_available if stock else 0


class DepartmentRequestSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.get_full_name", read_only=True
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True
    )
    total_estimated_cost = serializers.SerializerMethodField()
    lines = DepartmentRequestLineSerializer(many=True)

    class Meta:
        model = DepartmentRequest
        fields = [
            "id",
            "request_number",
            "department",
            "warehouse",
            "warehouse_name",
            "priority",
            "purpose",
            "needed_by_date",
            "status",
            "notes",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "issued_at",
            "rejection_reason",
            "approval_comment",
            "total_estimated_cost",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "request_number",
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "issued_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]

    def get_total_estimated_cost(self, obj):
        total = 0
        for line in obj.lines.all():
            qty = line.requested_qty or line.quantity
            total += qty * line.item.unit_cost
        return total

    def validate_lines(self, lines_data):
        from apps.inventory.models import Item

        for line in lines_data:
            item = line.get("item")
            if item and item.item_usage == Item.USAGE_FOR_SALE:
                raise serializers.ValidationError(
                    f"Item {item.code} is for sale only and cannot be requisitioned internally."
                )
        return lines_data

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        request = self.context.get("request")
        submit = self.context.get("submit", False)
        status = DepartmentRequest.STATUS_SUBMITTED if submit else DepartmentRequest.STATUS_DRAFT
        dept_request = DepartmentRequest.objects.create(
            request_number=create_dept_request_number(),
            requested_by=request.user,
            status=status,
            **validated_data,
        )
        for line in lines_data:
            qty = line.pop("requested_qty", None) or line.get("quantity")
            line["quantity"] = qty
            line["requested_qty"] = qty
            DepartmentRequestLine.objects.create(request=dept_request, **line)
        if submit:
            from apps.inventory.workflow import notify_request_submitted

            notify_request_submitted(dept_request)
        return dept_request


class GoodsIssueLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = GoodsIssueLine
        fields = ["id", "item", "item_code", "item_name", "quantity"]


class GoodsIssueNoteSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.get_full_name", read_only=True
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True
    )
    lines = GoodsIssueLineSerializer(many=True)

    class Meta:
        model = GoodsIssueNote
        fields = [
            "id",
            "gin_number",
            "department",
            "warehouse",
            "warehouse_name",
            "status",
            "reason",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "department_request",
            "issue_type",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "gin_number",
            "status",
            "requested_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        request = self.context.get("request")
        gin = GoodsIssueNote.objects.create(
            gin_number=create_gin_number(),
            requested_by=request.user,
            **validated_data,
        )
        for line in lines_data:
            GoodsIssueLine.objects.create(gin=gin, **line)
        return gin


class StockTakeLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = StockTakeLine
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "system_quantity",
            "physical_quantity",
            "variance",
            "reason",
        ]
        read_only_fields = ["variance"]


class StockTakeSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    conducted_by_name = serializers.CharField(
        source="conducted_by.get_full_name", read_only=True
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True
    )
    lines = StockTakeLineSerializer(many=True)

    class Meta:
        model = StockTake
        fields = [
            "id",
            "take_number",
            "warehouse",
            "warehouse_name",
            "status",
            "notes",
            "conducted_by",
            "conducted_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "take_number",
            "status",
            "conducted_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        request = self.context.get("request")
        stock_take = StockTake.objects.create(
            take_number=create_stock_take_number(),
            conducted_by=request.user,
            **validated_data,
        )
        for line in lines_data:
            StockTakeLine.objects.create(stock_take=stock_take, **line)
        return stock_take
