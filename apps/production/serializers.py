"""Serializers for the production module."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.production.models import (
    BillOfMaterials,
    BOMItem,
    FinishedGoodsReceipt,
    Machine,
    MachineServiceRecord,
    MachineUsage,
    OutputRecord,
    Product,
    WorkOrder,
    WorkOrderExecutionEvent,
    WorkOrderMaterialIssue,
    WorkOrderPauseRecord,
    WorkOrderPendingMaterial,
    WorkOrderProgressEntry,
)
from apps.production.services import ProductionService
from apps.production.utils import generate_document_number, generate_machine_code


class ProductSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    active_bom_id = serializers.SerializerMethodField()
    active_bom_version = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "item",
            "item_id",
            "item_code",
            "item_name",
            "name",
            "specifications",
            "standard_output",
            "unit_of_measure",
            "active_bom_id",
            "active_bom_version",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_active_bom_id(self, obj):
        bom = obj.boms.filter(status=BillOfMaterials.STATUS_ACTIVE, is_active=True).first()
        return bom.id if bom else None

    def get_active_bom_version(self, obj):
        bom = obj.boms.filter(status=BillOfMaterials.STATUS_ACTIVE, is_active=True).first()
        return bom.version if bom else None


class BOMItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    unit_of_measure = serializers.CharField(source="item.unit_of_measure", read_only=True)
    effective_quantity = serializers.SerializerMethodField()
    unit_cost = serializers.DecimalField(
        source="item.unit_cost", max_digits=18, decimal_places=2, read_only=True
    )
    total_cost = serializers.SerializerMethodField()
    current_stock = serializers.SerializerMethodField()

    class Meta:
        model = BOMItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_code",
            "item_name",
            "quantity_required",
            "unit_of_measure",
            "wastage_percent",
            "effective_quantity",
            "unit_cost",
            "total_cost",
            "current_stock",
            "notes",
        ]
        read_only_fields = ["id"]

    def get_effective_quantity(self, obj):
        return obj.effective_quantity

    def get_total_cost(self, obj):
        return obj.effective_quantity * obj.item.unit_cost

    def get_current_stock(self, obj):
        return ProductionService.get_stock_level(obj.item_id)


class BOMSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    total_components = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    items = BOMItemSerializer(many=True)

    class Meta:
        model = BillOfMaterials
        fields = [
            "id",
            "product",
            "product_id",
            "product_name",
            "version",
            "status",
            "total_components",
            "material_cost_per_unit",
            "items",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "status",
            "material_cost_per_unit",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_total_components(self, obj):
        return obj.items.count()

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["created_by"] = self.context["request"].user
        bom = BillOfMaterials.objects.create(**validated_data)
        for item_data in items_data:
            BOMItem.objects.create(bom=bom, **item_data)
        ProductionService.recalculate_bom_cost(bom)
        return bom

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status == BillOfMaterials.STATUS_ACTIVE:
            raise serializers.ValidationError("Active BOMs cannot be edited. Duplicate instead.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                BOMItem.objects.create(bom=instance, **item_data)
        ProductionService.recalculate_bom_cost(instance)
        return instance


class MaterialIssueSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = WorkOrderMaterialIssue
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "quantity_issued",
            "quantity_returned",
            "wastage",
        ]


class MachineUsageSerializer(serializers.ModelSerializer):
    machine_id = serializers.SerializerMethodField()
    machine_name = serializers.SerializerMethodField()
    wo_id = serializers.SerializerMethodField()
    wo_number = serializers.SerializerMethodField()
    operator_id = serializers.SerializerMethodField()
    operator_name = serializers.SerializerMethodField()

    class Meta:
        model = MachineUsage
        fields = [
            "id",
            "machine",
            "machine_id",
            "machine_name",
            "work_order",
            "wo_id",
            "wo_number",
            "operator",
            "operator_id",
            "operator_name",
            "start_time",
            "end_time",
            "hours_used",
            "notes",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_machine_id(self, obj):
        return obj.machine_id

    def get_machine_name(self, obj):
        return obj.machine.name if obj.machine_id else ""

    def get_wo_id(self, obj):
        return obj.work_order_id

    def get_wo_number(self, obj):
        return obj.work_order.wo_number if obj.work_order_id else ""

    def get_operator_id(self, obj):
        return obj.operator_id

    def get_operator_name(self, obj):
        return obj.operator.get_full_name() if obj.operator_id else ""


class OutputRecordSerializer(serializers.ModelSerializer):
    wo_id = serializers.IntegerField(source="work_order.id", read_only=True)
    wo_number = serializers.CharField(source="work_order.wo_number", read_only=True)
    product_name = serializers.CharField(source="work_order.product.name", read_only=True)
    operator_id = serializers.IntegerField(source="operator.id", read_only=True)
    operator_name = serializers.CharField(source="operator.get_full_name", read_only=True)
    supervisor_id = serializers.IntegerField(
        source="supervisor.id", read_only=True, allow_null=True
    )
    supervisor_name = serializers.CharField(
        source="supervisor.get_full_name", read_only=True, allow_null=True
    )
    quality_checked_by_name = serializers.CharField(
        source="quality_checked_by.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = OutputRecord
        fields = [
            "id",
            "work_order",
            "wo_id",
            "wo_number",
            "batch_number",
            "product_name",
            "date",
            "shift",
            "quantity_produced",
            "quantity_rejected",
            "rejection_reason",
            "operator",
            "operator_id",
            "operator_name",
            "supervisor",
            "supervisor_id",
            "supervisor_name",
            "quality_checked",
            "quality_checked_by",
            "quality_checked_by_name",
            "qc_result",
            "qc_notes",
            "notes",
            "created_at",
        ]
        read_only_fields = [
            "batch_number",
            "quality_checked",
            "quality_checked_by",
            "qc_result",
            "created_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        validated_data["batch_number"] = generate_document_number(
            "BATCH", OutputRecord, "batch_number"
        )
        if validated_data.get("quantity_rejected", 0) > 0 and not validated_data.get(
            "rejection_reason"
        ):
            raise serializers.ValidationError(
                {"rejection_reason": "Required when quantity rejected > 0."}
            )
        record = OutputRecord.objects.create(**validated_data)
        wo = record.work_order
        if wo.execution_workflow:
            wo.quantity_produced += record.quantity_produced
            wo.quantity_rejected += record.quantity_rejected
            wo.save(update_fields=["quantity_produced", "quantity_rejected", "updated_at"])
        else:
            ProductionService.record_output(record)
        return record


class PendingMaterialSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = WorkOrderPendingMaterial
        fields = [
            "id",
            "item",
            "item_code",
            "item_name",
            "quantity_consumed",
            "waste_quantity",
            "posted",
            "created_at",
        ]


class ProgressEntrySerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(source="recorded_by.get_full_name", read_only=True)

    class Meta:
        model = WorkOrderProgressEntry
        fields = [
            "id",
            "quantity_produced",
            "quantity_defective",
            "progress_percent",
            "machine_notes",
            "recorded_by_name",
            "created_at",
        ]


class PauseRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrderPauseRecord
        fields = ["id", "reason", "paused_at", "resumed_at", "downtime_minutes"]


class ExecutionEventSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True, allow_null=True)

    class Meta:
        model = WorkOrderExecutionEvent
        fields = ["id", "action", "old_status", "new_status", "payload", "user_name", "created_at"]


class FinishedGoodsReceiptSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    received_by_name = serializers.CharField(source="received_by.get_full_name", read_only=True)

    class Meta:
        model = FinishedGoodsReceipt
        fields = [
            "id",
            "warehouse",
            "warehouse_name",
            "quantity_received",
            "batch_number",
            "notes",
            "posted",
            "received_by_name",
            "created_at",
        ]


class AssignOperatorSerializer(serializers.Serializer):
    operator = serializers.IntegerField()


class OperatorStartSerializer(serializers.Serializer):
    machine = serializers.IntegerField(required=False)


class PauseSerializer(serializers.Serializer):
    reason = serializers.CharField()


class ProgressSerializer(serializers.Serializer):
    quantity_produced = serializers.DecimalField(max_digits=18, decimal_places=4)
    quantity_defective = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("0")
    )
    machine_notes = serializers.CharField(required=False, allow_blank=True, default="")


class ConsumptionLineSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity_consumed = serializers.DecimalField(max_digits=18, decimal_places=4)
    waste_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("0")
    )


class ConsumptionSerializer(serializers.Serializer):
    lines = ConsumptionLineSerializer(many=True)


class SubmitCompletionSerializer(serializers.Serializer):
    quantity_produced = serializers.DecimalField(max_digits=18, decimal_places=4)
    quantity_defective = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("0")
    )
    machine_condition = serializers.CharField(required=False, allow_blank=True, default="")
    completion_notes = serializers.CharField(required=False, allow_blank=True, default="")


class StoreReceiptSerializer(serializers.Serializer):
    warehouse = serializers.IntegerField()
    quantity_received = serializers.DecimalField(max_digits=18, decimal_places=4)
    batch_number = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class MachineRuntimeSerializer(serializers.Serializer):
    condition = serializers.ChoiceField(choices=Machine.RUNTIME_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    work_order = serializers.IntegerField(required=False)


class WorkOrderSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_specifications = serializers.JSONField(
        source="product.specifications", read_only=True
    )
    bom_id = serializers.IntegerField(source="bom.id", read_only=True)
    bom_version = serializers.CharField(source="bom.version", read_only=True)
    so_id = serializers.IntegerField(source="sales_order.id", read_only=True, allow_null=True)
    so_number = serializers.CharField(
        source="sales_order.so_number", read_only=True, allow_null=True
    )
    operator_id = serializers.IntegerField(source="operator.id", read_only=True)
    operator_name = serializers.CharField(source="operator.get_full_name", read_only=True)
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True, allow_null=True
    )
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    material_requirements = serializers.SerializerMethodField()
    material_issues = MaterialIssueSerializer(many=True, read_only=True)
    pending_materials = PendingMaterialSerializer(many=True, read_only=True)
    progress_entries = ProgressEntrySerializer(many=True, read_only=True)
    pause_records = PauseRecordSerializer(many=True, read_only=True)
    execution_events = ExecutionEventSerializer(many=True, read_only=True)
    finished_goods_receipt = FinishedGoodsReceiptSerializer(read_only=True)
    output_records = OutputRecordSerializer(many=True, read_only=True)
    machine_usage = MachineUsageSerializer(many=True, read_only=True)
    can_start = serializers.SerializerMethodField()
    can_operator_start = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    rejection_rate = serializers.SerializerMethodField()
    production_approved_by_name = serializers.CharField(
        source="production_approved_by.get_full_name", read_only=True, allow_null=True
    )
    store_received_by_name = serializers.CharField(
        source="store_received_by.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = WorkOrder
        fields = [
            "id",
            "wo_number",
            "product",
            "product_id",
            "product_name",
            "product_specifications",
            "bom",
            "bom_id",
            "bom_version",
            "sales_order",
            "so_id",
            "so_number",
            "machine",
            "quantity_planned",
            "quantity_produced",
            "quantity_rejected",
            "planned_start",
            "planned_end",
            "actual_start",
            "actual_end",
            "shift",
            "status",
            "priority",
            "production_line",
            "execution_workflow",
            "assigned_at",
            "completion_notes",
            "machine_condition",
            "operator",
            "operator_id",
            "operator_name",
            "material_requirements",
            "material_issues",
            "pending_materials",
            "progress_entries",
            "pause_records",
            "execution_events",
            "finished_goods_receipt",
            "output_records",
            "machine_usage",
            "materials_issued",
            "can_start",
            "can_operator_start",
            "progress_percent",
            "rejection_rate",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "production_approved_by",
            "production_approved_by_name",
            "production_approved_at",
            "store_received_by",
            "store_received_by_name",
            "store_received_at",
            "created_by",
            "created_by_name",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "wo_number",
            "status",
            "quantity_produced",
            "quantity_rejected",
            "actual_start",
            "actual_end",
            "materials_issued",
            "approved_by",
            "approved_at",
            "assigned_at",
            "production_approved_by",
            "production_approved_at",
            "store_received_by",
            "store_received_at",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_material_requirements(self, obj):
        return ProductionService.material_requirements(obj.bom, obj.quantity_planned)

    def get_can_start(self, obj):
        if obj.execution_workflow:
            return False
        return (
            obj.status == WorkOrder.STATUS_APPROVED
            and ProductionService.all_materials_sufficient(obj.bom, obj.quantity_planned)
        )

    def get_can_operator_start(self, obj):
        return obj.execution_workflow and obj.status in (
            WorkOrder.STATUS_ASSIGNED,
            WorkOrder.STATUS_APPROVED,
        )

    def get_progress_percent(self, obj):
        if obj.quantity_planned <= 0:
            return 0
        return float(
            (obj.quantity_produced / obj.quantity_planned * 100).quantize(Decimal("0.1"))
        )

    def get_rejection_rate(self, obj):
        total = obj.quantity_produced + obj.quantity_rejected
        if total <= 0:
            return 0
        return float((obj.quantity_rejected / total * 100).quantize(Decimal("0.1")))

    @transaction.atomic
    def create(self, validated_data):
        validated_data["wo_number"] = generate_document_number("WO", WorkOrder, "wo_number")
        validated_data["created_by"] = self.context["request"].user
        validated_data.setdefault("execution_workflow", True)
        if not validated_data.get("bom"):
            product = validated_data["product"]
            bom = product.boms.filter(
                status=BillOfMaterials.STATUS_ACTIVE, is_active=True
            ).first()
            if not bom:
                raise serializers.ValidationError("Product has no active BOM.")
            validated_data["bom"] = bom
        return WorkOrder.objects.create(**validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != WorkOrder.STATUS_DRAFT:
            raise serializers.ValidationError("Only draft work orders can be edited.")
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class MachineSerializer(serializers.ModelSerializer):
    hours_this_month = serializers.SerializerMethodField()
    utilization_rate = serializers.SerializerMethodField()
    current_wo = serializers.SerializerMethodField()

    class Meta:
        model = Machine
        fields = [
            "id",
            "machine_code",
            "name",
            "machine_type",
            "purchase_date",
            "status",
            "last_service_date",
            "next_service_date",
            "hours_this_month",
            "utilization_rate",
            "current_wo",
            "runtime_condition",
            "runtime_notes",
            "runtime_updated_at",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_hours_this_month(self, obj):
        return ProductionService.machine_hours_this_month(obj)

    def get_utilization_rate(self, obj):
        hours = ProductionService.machine_hours_this_month(obj)
        # Assume 160 working hours per month as 100% utilization
        return float(min(hours / Decimal("160") * 100, Decimal("100")).quantize(Decimal("0.1")))

    def get_current_wo(self, obj):
        wo = WorkOrder.objects.filter(
            machine=obj, status=WorkOrder.STATUS_IN_PROGRESS, is_active=True
        ).values("wo_number", "id").first()
        return wo

    def create(self, validated_data):
        if not validated_data.get("machine_code"):
            validated_data["machine_code"] = generate_machine_code(Machine)
        return super().create(validated_data)


class MachineServiceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineServiceRecord
        fields = [
            "id",
            "machine",
            "service_date",
            "description",
            "cost",
            "performed_by",
            "next_service_date",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class QCCheckSerializer(serializers.Serializer):
    qc_result = serializers.ChoiceField(choices=["PASS", "FAIL"])
    qc_notes = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


class MaterialCheckSerializer(serializers.Serializer):
    bom_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
