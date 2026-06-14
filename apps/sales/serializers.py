"""Serializers for the sales module."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.sales.models import (
    CreditNote,
    Customer,
    CustomerPayment,
    SalesInvoice,
    SalesInvoiceItem,
    SalesOrder,
    SalesOrderActivity,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationItem,
)
from apps.sales.services import SalesService
from apps.sales.utils import generate_document_number
from apps.sales.workflow_serializers import (
    DeliveryCostSerializer,
    DispatchAssignmentSerializer,
    PaymentProofSerializer,
    PickupDetailSerializer,
)

DEFAULT_TERMS = (
    "Payment terms as agreed. Goods remain property of Rock Solutions Limited "
    "until fully paid. Prices are valid for the period stated on this quotation."
)


class CustomerSerializer(serializers.ModelSerializer):
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    credit_balance = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()
    total_invoiced = serializers.SerializerMethodField()
    total_paid = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
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
            "mine_name",
            "mine_location",
            "mine_type",
            "contact_person",
            "contact_phone",
            "currency",
            "currency_id",
            "currency_code",
            "credit_limit",
            "credit_balance",
            "payment_terms",
            "is_active",
            "total_orders",
            "total_invoiced",
            "total_paid",
            "outstanding_balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_credit_balance(self, obj):
        return SalesService.customer_credit_balance(obj)

    def get_total_orders(self, obj):
        return obj.sales_orders.filter(is_active=True).count()

    def get_total_invoiced(self, obj):
        return sum(
            (i.total_amount for i in obj.invoices.filter(is_active=True)),
            Decimal("0"),
        )

    def get_total_paid(self, obj):
        return sum(
            (p.amount for p in obj.payments.filter(is_active=True)),
            Decimal("0"),
        )

    def get_outstanding_balance(self, obj):
        return SalesService.customer_outstanding(obj)


class QuotationItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = SalesQuotationItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_code",
            "item_name",
            "description",
            "quantity",
            "unit_price",
            "discount_percent",
            "total_price",
        ]
        read_only_fields = ["id", "total_price"]


class QuotationSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    mine_name = serializers.CharField(source="customer.mine_name", read_only=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    items = QuotationItemSerializer(many=True)
    is_expired = serializers.SerializerMethodField()
    has_sales_order = serializers.SerializerMethodField()

    class Meta:
        model = SalesQuotation
        fields = [
            "id",
            "quotation_number",
            "customer",
            "customer_id",
            "customer_name",
            "mine_name",
            "currency",
            "currency_id",
            "currency_code",
            "exchange_rate",
            "valid_until",
            "status",
            "apply_vat",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "delivery_cost",
            "notes",
            "terms_conditions",
            "items",
            "is_expired",
            "has_sales_order",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "quotation_number",
            "status",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_is_expired(self, obj):
        return obj.valid_until < timezone.now().date()

    def get_has_sales_order(self, obj):
        return obj.sales_orders.filter(is_active=True).exists()

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["quotation_number"] = generate_document_number(
            "QT", SalesQuotation, "quotation_number"
        )
        validated_data["created_by"] = self.context["request"].user
        if not validated_data.get("terms_conditions"):
            validated_data["terms_conditions"] = DEFAULT_TERMS
        quotation = SalesQuotation.objects.create(**validated_data)
        for item_data in items_data:
            SalesQuotationItem.objects.create(quotation=quotation, **item_data)
        SalesService.recalculate_quotation(quotation)
        return quotation

    @transaction.atomic
    def update(self, instance, validated_data):
        if not SalesService.quotation_is_editable(instance):
            raise serializers.ValidationError(
                "This quotation cannot be edited (converted, rejected, or expired)."
            )
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                SalesQuotationItem.objects.create(quotation=instance, **item_data)
        SalesService.recalculate_quotation(instance)
        return instance


class SOItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    stock_available = serializers.SerializerMethodField()

    class Meta:
        model = SalesOrderItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_code",
            "item_name",
            "quantity_ordered",
            "quantity_delivered",
            "quantity_reserved",
            "stock_available_snapshot",
            "unit_price",
            "discount_percent",
            "total_price",
            "stock_available",
        ]
        read_only_fields = [
            "id",
            "total_price",
            "quantity_delivered",
            "quantity_reserved",
            "stock_available_snapshot",
        ]

    def get_stock_available(self, obj):
        return SalesService.get_stock_available(obj.item_id)


class SOActivitySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True, allow_null=True)

    class Meta:
        model = SalesOrderActivity
        fields = [
            "id",
            "action",
            "previous_status",
            "new_status",
            "details",
            "remarks",
            "user_name",
            "created_at",
        ]


class SalesOrderSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    quotation_id = serializers.IntegerField(source="quotation.id", read_only=True, allow_null=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True, allow_null=True
    )
    items = SOItemSerializer(many=True)
    activities = SOActivitySerializer(many=True, read_only=True)
    warehouse_id = serializers.IntegerField(
        source="fulfillment_warehouse.id", read_only=True, allow_null=True
    )
    warehouse_name = serializers.CharField(
        source="fulfillment_warehouse.name", read_only=True, allow_null=True
    )
    delivery_cost_detail = DeliveryCostSerializer(read_only=True)
    dispatch_assignment = DispatchAssignmentSerializer(read_only=True)
    pickup_detail = PickupDetailSerializer(read_only=True)
    payment_proofs = PaymentProofSerializer(many=True, read_only=True)
    linked_pr_number = serializers.CharField(
        source="linked_pr.pr_number", read_only=True, allow_null=True
    )

    class Meta:
        model = SalesOrder
        fields = [
            "id",
            "so_number",
            "customer",
            "customer_id",
            "customer_name",
            "quotation",
            "quotation_id",
            "lpo_number",
            "lpo_date",
            "currency",
            "currency_id",
            "currency_code",
            "exchange_rate",
            "delivery_date",
            "delivery_address",
            "requested_delivery_location",
            "fulfillment_warehouse",
            "warehouse_id",
            "warehouse_name",
            "status",
            "inventory_status",
            "delivery_method",
            "delivery_cost",
            "delivery_status",
            "payment_status",
            "apply_vat",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "notes",
            "items",
            "activities",
            "delivery_cost_detail",
            "dispatch_assignment",
            "pickup_detail",
            "payment_proofs",
            "linked_pr",
            "linked_pr_number",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "cancel_reason",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "so_number",
            "status",
            "delivery_status",
            "payment_status",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "approved_by",
            "approved_at",
            "created_by",
            "created_at",
            "updated_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["so_number"] = generate_document_number("SO", SalesOrder, "so_number")
        validated_data["created_by"] = self.context["request"].user
        if not validated_data.get("delivery_address"):
            customer = validated_data["customer"]
            validated_data["delivery_address"] = customer.address
        if not validated_data.get("requested_delivery_location"):
            validated_data["requested_delivery_location"] = validated_data.get(
                "delivery_address", ""
            )
        validated_data.setdefault("status", SalesOrder.STATUS_NEW_ORDER)
        order = SalesOrder.objects.create(**validated_data)
        for item_data in items_data:
            SalesOrderItem.objects.create(sales_order=order, **item_data)
        SalesService.recalculate_order(order)
        SalesService.log_activity(order, "Created", validated_data["created_by"], "Sales order created")
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        from apps.sales.workflow import SalesOrderWorkflow

        if instance.status not in SalesOrderWorkflow.EDITABLE_STATUSES:
            raise serializers.ValidationError("This sales order cannot be edited at its current stage.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                SalesOrderItem.objects.create(sales_order=instance, **item_data)
        SalesService.recalculate_order(instance)
        return instance


class InvoiceItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_code = serializers.CharField(source="item.code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = SalesInvoiceItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_code",
            "item_name",
            "quantity",
            "unit_price",
            "discount_percent",
            "tax_rate",
            "total_price",
        ]
        read_only_fields = ["id", "total_price"]


class InvoiceSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_tin = serializers.CharField(source="customer.tin_number", read_only=True)
    so_id = serializers.IntegerField(source="sales_order.id", read_only=True, allow_null=True)
    so_number = serializers.CharField(source="sales_order.so_number", read_only=True, allow_null=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    balance = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    items = InvoiceItemSerializer(many=True)

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "invoice_number",
            "sales_order",
            "so_id",
            "so_number",
            "customer",
            "customer_id",
            "customer_name",
            "customer_tin",
            "currency",
            "currency_id",
            "currency_code",
            "exchange_rate",
            "invoice_date",
            "due_date",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "delivery_cost",
            "paid_amount",
            "balance",
            "status",
            "tra_receipt_number",
            "items",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "invoice_number",
            "status",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total_amount",
            "paid_amount",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_balance(self, obj):
        return obj.balance

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        validated_data["invoice_number"] = generate_document_number(
            "INV", SalesInvoice, "invoice_number"
        )
        validated_data["created_by"] = self.context["request"].user
        invoice = SalesInvoice.objects.create(**validated_data)
        for item_data in items_data:
            SalesInvoiceItem.objects.create(invoice=invoice, **item_data)
        SalesService.recalculate_invoice(invoice)
        return invoice

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != SalesInvoice.STATUS_DRAFT:
            raise serializers.ValidationError("Only draft invoices can be edited.")
        items_data = validated_data.pop("items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                SalesInvoiceItem.objects.create(invoice=instance, **item_data)
        SalesService.recalculate_invoice(instance)
        return instance


class PaymentSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_id = serializers.IntegerField(source="invoice.id", read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    received_by_name = serializers.CharField(source="received_by.get_full_name", read_only=True)

    class Meta:
        model = CustomerPayment
        fields = [
            "id",
            "payment_number",
            "customer",
            "customer_id",
            "customer_name",
            "invoice",
            "invoice_id",
            "invoice_number",
            "currency",
            "currency_id",
            "currency_code",
            "amount",
            "payment_date",
            "payment_method",
            "reference_number",
            "bank_name",
            "notes",
            "received_by",
            "received_by_name",
            "created_at",
        ]
        read_only_fields = ["payment_number", "received_by", "created_at"]

    @transaction.atomic
    def create(self, validated_data):
        invoice = validated_data["invoice"]
        balance = invoice.balance
        if validated_data["amount"] > balance:
            raise serializers.ValidationError(
                {"amount": f"Amount cannot exceed invoice balance ({balance})."}
            )
        validated_data["payment_number"] = generate_document_number(
            "PAY", CustomerPayment, "payment_number"
        )
        validated_data["customer"] = invoice.customer
        validated_data["currency"] = invoice.currency
        validated_data["received_by"] = self.context["request"].user
        payment = CustomerPayment.objects.create(**validated_data)
        SalesService.record_payment(payment)
        return payment


class CreditNoteSerializer(serializers.ModelSerializer):
    invoice_id = serializers.IntegerField(source="invoice.id", read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    approved_by_name = serializers.CharField(
        source="approved_by.get_full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = CreditNote
        fields = [
            "id",
            "cn_number",
            "invoice",
            "invoice_id",
            "invoice_number",
            "customer",
            "customer_id",
            "customer_name",
            "reason",
            "amount",
            "notes",
            "status",
            "created_by",
            "created_by_name",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "created_at",
        ]
        read_only_fields = [
            "cn_number",
            "status",
            "customer",
            "created_by",
            "approved_by",
            "approved_at",
            "created_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        invoice = validated_data["invoice"]
        if validated_data["amount"] > invoice.total_amount:
            raise serializers.ValidationError(
                {"amount": "Amount cannot exceed invoice total."}
            )
        validated_data["cn_number"] = generate_document_number("CN", CreditNote, "cn_number")
        validated_data["customer"] = invoice.customer
        validated_data["created_by"] = self.context["request"].user
        return CreditNote.objects.create(**validated_data)


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True)
