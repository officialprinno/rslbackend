"""Serializers for the procurement module."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.procurement.models import (
    GRNItem,
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    RequestForQuotation,
    RFQSupplier,
    Supplier,
    SupplierInvoice,
    SupplierQuotation,
    SupplierQuotationItem,
)
from apps.procurement.services import ProcurementService
from apps.procurement.utils import generate_document_number


class SupplierSerializer(serializers.ModelSerializer):
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    total_pos = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()
    last_order_date = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "registration_number",
            "tin_number",
            "vat_number",
            "email",
            "phone",
            "address",
            "city",
            "country",
            "currency",
            "currency_id",
            "currency_code",
            "payment_terms",
            "rating",
            "is_active",
            "total_pos",
            "total_value",
            "last_order_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_total_pos(self, obj):
        return obj.purchase_orders.filter(is_active=True).count()

    def get_total_value(self, obj):
        return sum(
            (po.total_amount for po in obj.purchase_orders.filter(is_active=True)),
            Decimal("0"),
        )

    def get_last_order_date(self, obj):
        last = (
            obj.purchase_orders.filter(is_active=True)
            .order_by("-order_date")
            .values_list("order_date", flat=True)
            .first()
        )
        return last.isoformat() if last else None


class PRItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)

    class Meta:
        model = PurchaseRequisitionItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_name",
            "item_code",
            "quantity_requested",
            "unit_cost_estimate",
            "total_estimate",
            "notes",
        ]
        read_only_fields = ["id", "total_estimate"]


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField(source="department.id", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.get_full_name",
        read_only=True,
    )
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name",
        read_only=True,
        allow_null=True,
    )
    items = PRItemSerializer(many=True)

    class Meta:
        model = PurchaseRequisition
        fields = [
            "id",
            "pr_number",
            "department",
            "department_id",
            "department_name",
            "priority",
            "status",
            "notes",
            "items",
            "total_estimated",
            "requested_by",
            "requested_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "pr_number",
            "status",
            "total_estimated",
            "requested_by",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context["request"]
        validated_data["requested_by"] = request.user
        validated_data["pr_number"] = generate_document_number(
            "PR", PurchaseRequisition, "pr_number"
        )
        if not validated_data.get("department") and request.user.department:
            validated_data["department"] = request.user.department
        pr = PurchaseRequisition.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseRequisitionItem.objects.create(requisition=pr, **item_data)
        ProcurementService.recalculate_requisition_total(pr)
        pr.refresh_from_db()
        return pr

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != PurchaseRequisition.STATUS_DRAFT:
            raise serializers.ValidationError("Only draft requisitions can be edited.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseRequisitionItem.objects.create(requisition=instance, **item_data)
        ProcurementService.recalculate_requisition_total(instance)
        instance.refresh_from_db()
        return instance


class RFQSupplierSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    supplier_rating = serializers.IntegerField(source="supplier.rating", read_only=True)

    class Meta:
        model = RFQSupplier
        fields = ["id", "supplier", "supplier_name", "supplier_rating"]


class RFQSerializer(serializers.ModelSerializer):
    pr_number = serializers.CharField(source="requisition.pr_number", read_only=True)
    requisition_id = serializers.IntegerField(source="requisition.id", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    suppliers_count = serializers.SerializerMethodField()
    supplier_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )
    invited_suppliers = RFQSupplierSerializer(
        source="rfqsupplier_set",
        many=True,
        read_only=True,
    )
    items = PRItemSerializer(source="requisition.items", many=True, read_only=True)

    class Meta:
        model = RequestForQuotation
        fields = [
            "id",
            "rfq_number",
            "requisition",
            "requisition_id",
            "pr_number",
            "deadline",
            "status",
            "notes",
            "suppliers_count",
            "supplier_ids",
            "invited_suppliers",
            "items",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["rfq_number", "status", "created_by", "created_at", "updated_at"]

    def get_suppliers_count(self, obj):
        return obj.suppliers.count()

    @transaction.atomic
    def create(self, validated_data):
        supplier_ids = validated_data.pop("supplier_ids", [])
        validated_data["created_by"] = self.context["request"].user
        validated_data["rfq_number"] = generate_document_number(
            "RFQ", RequestForQuotation, "rfq_number"
        )
        rfq = RequestForQuotation.objects.create(**validated_data)
        for sid in supplier_ids:
            RFQSupplier.objects.create(rfq=rfq, supplier_id=sid)
        return rfq


class QuotationItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)

    class Meta:
        model = SupplierQuotationItem
        fields = [
            "id",
            "item",
            "item_name",
            "item_code",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = ["id", "total_price"]


class QuotationSerializer(serializers.ModelSerializer):
    rfq_number = serializers.CharField(source="rfq.rfq_number", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    items = QuotationItemSerializer(many=True)

    class Meta:
        model = SupplierQuotation
        fields = [
            "id",
            "quotation_number",
            "rfq",
            "rfq_number",
            "supplier",
            "supplier_name",
            "quotation_date",
            "valid_until",
            "currency",
            "currency_code",
            "exchange_rate",
            "delivery_days",
            "total_amount",
            "status",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["total_amount", "status", "created_at", "updated_at"]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        quotation = SupplierQuotation.objects.create(**validated_data)
        for item_data in items_data:
            SupplierQuotationItem.objects.create(quotation=quotation, **item_data)
        ProcurementService.recalculate_quotation_total(quotation)
        quotation.refresh_from_db()
        return quotation


class POItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    has_serial_number = serializers.BooleanField(
        source="item.has_serial_number",
        read_only=True,
    )
    has_expiry_date = serializers.BooleanField(
        source="item.has_expiry_date",
        read_only=True,
    )

    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_name",
            "item_code",
            "has_serial_number",
            "has_expiry_date",
            "quantity_ordered",
            "quantity_received",
            "unit_price",
            "discount_percent",
            "total_price",
        ]
        read_only_fields = ["id", "quantity_received", "total_price"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_id = serializers.IntegerField(source="supplier.id", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    pr_id = serializers.IntegerField(source="requisition.id", read_only=True, allow_null=True)
    quotation_id = serializers.IntegerField(source="quotation.id", read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name",
        read_only=True,
        allow_null=True,
    )
    items = POItemSerializer(many=True)
    grn_history = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "po_number",
            "supplier",
            "supplier_id",
            "supplier_name",
            "quotation",
            "quotation_id",
            "requisition",
            "pr_id",
            "currency",
            "currency_id",
            "currency_code",
            "exchange_rate",
            "order_date",
            "expected_delivery",
            "payment_terms",
            "subtotal",
            "tax_amount",
            "apply_vat",
            "total_amount",
            "status",
            "notes",
            "items",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "rejection_reason",
            "created_by",
            "created_by_name",
            "grn_history",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "po_number",
            "status",
            "subtotal",
            "tax_amount",
            "total_amount",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_grn_history(self, obj):
        return [
            {
                "id": g.id,
                "grn_number": g.grn_number,
                "received_date": g.received_date.isoformat(),
                "status": g.status,
            }
            for g in obj.grns.filter(is_active=True).order_by("-received_date")
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["created_by"] = self.context["request"].user
        validated_data["po_number"] = generate_document_number(
            "PO", PurchaseOrder, "po_number"
        )
        po = PurchaseOrder.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseOrderItem.objects.create(purchase_order=po, **item_data)
        ProcurementService.recalculate_po_totals(po)
        po.refresh_from_db()
        return po

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != PurchaseOrder.STATUS_DRAFT:
            raise serializers.ValidationError("Only draft POs can be edited.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseOrderItem.objects.create(purchase_order=instance, **item_data)
        ProcurementService.recalculate_po_totals(instance)
        instance.refresh_from_db()
        return instance


class GRNItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    has_serial_number = serializers.BooleanField(
        source="item.has_serial_number",
        read_only=True,
    )
    has_expiry_date = serializers.BooleanField(
        source="item.has_expiry_date",
        read_only=True,
    )
    quantity_ordered = serializers.DecimalField(
        source="po_item.quantity_ordered",
        max_digits=18,
        decimal_places=4,
        read_only=True,
    )
    quantity_previously_received = serializers.DecimalField(
        source="po_item.quantity_received",
        max_digits=18,
        decimal_places=4,
        read_only=True,
    )
    serial_number = serializers.CharField(
        allow_blank=True,
        allow_null=True,
        required=False,
        default="",
    )
    notes = serializers.CharField(allow_blank=True, allow_null=True, required=False, default="")
    expiry_date = serializers.DateField(allow_null=True, required=False)

    class Meta:
        model = GRNItem
        fields = [
            "id",
            "po_item",
            "item",
            "item_id",
            "item_name",
            "item_code",
            "has_serial_number",
            "has_expiry_date",
            "quantity_ordered",
            "quantity_previously_received",
            "quantity_received",
            "unit_cost",
            "serial_number",
            "expiry_date",
            "condition",
            "notes",
        ]

    def validate_serial_number(self, value):
        return value or ""

    def validate_notes(self, value):
        return value or ""

    def validate(self, attrs):
        po_item = attrs.get("po_item") or getattr(self.instance, "po_item", None)
        item = attrs.get("item") or getattr(self.instance, "item", None)
        if po_item and item and po_item.item_id != item.id:
            raise serializers.ValidationError(
                {"item": "Item must match the purchase order line."}
            )
        qty = attrs.get("quantity_received")
        if qty is None and self.instance is not None:
            qty = self.instance.quantity_received
        qty = qty or Decimal("0")

        if po_item and qty > 0:
            remaining = po_item.quantity_ordered - po_item.quantity_received
            if qty > remaining:
                raise serializers.ValidationError(
                    {
                        "quantity_received": (
                            f"Cannot receive {qty}; only {remaining} remaining on this PO line."
                        )
                    }
                )

        if item and item.has_serial_number and not attrs.get("serial_number"):
            if qty > 0:
                raise serializers.ValidationError(
                    {"serial_number": "Serial number is required for this item."}
                )

        if item and item.has_expiry_date and not attrs.get("expiry_date"):
            if qty > 0:
                raise serializers.ValidationError(
                    {"expiry_date": "Expiry date is required for this item."}
                )
        return attrs


class GRNSerializer(serializers.ModelSerializer):
    po_number = serializers.CharField(source="purchase_order.po_number", read_only=True)
    po_id = serializers.IntegerField(source="purchase_order.id", read_only=True)
    supplier_id = serializers.IntegerField(
        source="purchase_order.supplier.id",
        read_only=True,
    )
    supplier_name = serializers.CharField(
        source="purchase_order.supplier.name",
        read_only=True,
    )
    warehouse_id = serializers.IntegerField(source="warehouse.id", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    received_by_name = serializers.CharField(
        source="received_by.get_full_name",
        read_only=True,
    )
    items = GRNItemSerializer(many=True)

    class Meta:
        model = GoodsReceivedNote
        fields = [
            "id",
            "grn_number",
            "purchase_order",
            "po_id",
            "po_number",
            "supplier_id",
            "supplier_name",
            "warehouse",
            "warehouse_id",
            "warehouse_name",
            "received_date",
            "received_by",
            "received_by_name",
            "status",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "grn_number",
            "status",
            "received_by",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        items = attrs.get("items") or (
            list(self.instance.items.all()) if self.instance else []
        )
        if not items:
            raise serializers.ValidationError({"items": "At least one GRN line is required."})

        has_receipt = False
        for line in items:
            if isinstance(line, dict):
                qty = line.get("quantity_received") or Decimal("0")
            else:
                qty = line.quantity_received
            if qty and qty > 0:
                has_receipt = True
                break
        if not has_receipt:
            raise serializers.ValidationError(
                {"items": "Enter a received quantity greater than zero on at least one line."}
            )

        purchase_order = attrs.get("purchase_order") or getattr(
            self.instance, "purchase_order", None
        )
        if purchase_order and purchase_order.status not in (
            PurchaseOrder.STATUS_APPROVED,
            PurchaseOrder.STATUS_SENT,
            PurchaseOrder.STATUS_PARTIAL,
        ):
            raise serializers.ValidationError(
                {
                    "purchase_order": (
                        "Goods can only be received against approved, sent, or partial POs."
                    )
                }
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["received_by"] = self.context["request"].user
        validated_data["grn_number"] = generate_document_number(
            "GRN", GoodsReceivedNote, "grn_number"
        )
        grn = GoodsReceivedNote.objects.create(**validated_data)
        for item_data in items_data:
            GRNItem.objects.create(grn=grn, **item_data)
        return grn

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != GoodsReceivedNote.STATUS_DRAFT:
            raise serializers.ValidationError("Only draft GRNs can be edited.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                GRNItem.objects.create(grn=instance, **item_data)
        return instance


class SupplierInvoiceSerializer(serializers.ModelSerializer):
    supplier_id = serializers.IntegerField(source="supplier.id", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    po_number = serializers.CharField(source="purchase_order.po_number", read_only=True)
    po_id = serializers.IntegerField(source="purchase_order.id", read_only=True)
    grn_number = serializers.CharField(source="grn.grn_number", read_only=True)
    grn_id = serializers.IntegerField(source="grn.id", read_only=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    balance = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    po_amount = serializers.DecimalField(
        source="purchase_order.total_amount",
        max_digits=18,
        decimal_places=2,
        read_only=True,
    )
    grn_amount = serializers.SerializerMethodField()

    class Meta:
        model = SupplierInvoice
        fields = [
            "id",
            "invoice_number",
            "supplier",
            "supplier_id",
            "supplier_name",
            "purchase_order",
            "po_id",
            "po_number",
            "grn",
            "grn_id",
            "grn_number",
            "invoice_date",
            "due_date",
            "currency",
            "currency_id",
            "currency_code",
            "exchange_rate",
            "subtotal",
            "tax_amount",
            "total_amount",
            "paid_amount",
            "balance",
            "three_way_matched",
            "status",
            "notes",
            "po_amount",
            "grn_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "paid_amount",
            "balance",
            "three_way_matched",
            "status",
            "created_at",
            "updated_at",
        ]

    def get_grn_amount(self, obj):
        return sum(
            (line.quantity_received * line.unit_cost for line in obj.grn.items.all()),
            Decimal("0"),
        )


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)


class PaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    payment_date = serializers.DateField(default=timezone.now)
    payment_method = serializers.CharField(max_length=50)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bank = serializers.CharField(max_length=100, required=False, allow_blank=True)
