"""
Sales models for Rock Solutions FMS.

Customers → Quotations → Sales Orders → Invoices → Payments / Credit Notes
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Customer(BaseModel):
    """Mining company customer."""

    PAYMENT_IMMEDIATE = "IMMEDIATE"
    PAYMENT_NET_15 = "NET_15"
    PAYMENT_NET_30 = "NET_30"
    PAYMENT_NET_60 = "NET_60"
    PAYMENT_TERMS_CHOICES = [
        (PAYMENT_IMMEDIATE, "Immediate"),
        (PAYMENT_NET_15, "Net 15"),
        (PAYMENT_NET_30, "Net 30"),
        (PAYMENT_NET_60, "Net 60"),
    ]

    MINE_UNDERGROUND = "UNDERGROUND"
    MINE_OPEN_PIT = "OPEN_PIT"
    MINE_BOTH = "BOTH"
    MINE_TYPE_CHOICES = [
        (MINE_UNDERGROUND, "Underground"),
        (MINE_OPEN_PIT, "Open Pit"),
        (MINE_BOTH, "Both"),
    ]

    name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=100, blank=True)
    tin_number = models.CharField(max_length=50)
    vat_number = models.CharField(max_length=50, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Tanzania")
    mine_name = models.CharField(max_length=255)
    mine_location = models.CharField(max_length=255, blank=True)
    mine_type = models.CharField(
        max_length=20,
        choices=MINE_TYPE_CHOICES,
        default=MINE_UNDERGROUND,
    )
    contact_person = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="customers",
    )
    credit_limit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    payment_terms = models.CharField(
        max_length=20,
        choices=PAYMENT_TERMS_CHOICES,
        default=PAYMENT_NET_30,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SalesQuotation(BaseModel):
    """Sales quotation / proposal."""

    STATUS_DRAFT = "DRAFT"
    STATUS_SENT = "SENT"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_EXPIRED, "Expired"),
    ]

    quotation_number = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="sales_quotations",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    valid_until = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    apply_vat = models.BooleanField(default=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    delivery_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_quotations",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.quotation_number


class SalesQuotationItem(models.Model):
    """Line item on a sales quotation."""

    quotation = models.ForeignKey(
        SalesQuotation,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="sales_quotation_lines",
    )
    description = models.TextField(blank=True)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["id"]


class SalesOrder(BaseModel):
    """Customer sales order — enterprise distribution workflow."""

    # Legacy statuses (kept for backward compatibility)
    STATUS_DRAFT = "DRAFT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_DELIVERED = "DELIVERED"

    # Enterprise workflow statuses
    STATUS_NEW_ORDER = "NEW_ORDER"
    STATUS_STOCK_VERIFICATION = "STOCK_VERIFICATION"
    STATUS_OUT_OF_STOCK = "OUT_OF_STOCK"
    STATUS_PENDING_DELIVERY_COST = "PENDING_DELIVERY_COST"
    STATUS_DELIVERY_COST_CALC = "DELIVERY_COST_CALC"
    STATUS_QUOTATION_PREP = "QUOTATION_PREP"
    STATUS_QUOTATION_SENT = "QUOTATION_SENT"
    STATUS_WAITING_CUSTOMER = "WAITING_CUSTOMER"
    STATUS_QUOTATION_ACCEPTED = "QUOTATION_ACCEPTED"
    STATUS_QUOTATION_REJECTED = "QUOTATION_REJECTED"
    STATUS_INVOICE_GENERATED = "INVOICE_GENERATED"
    STATUS_AWAITING_PAYMENT = "AWAITING_PAYMENT"
    STATUS_PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    STATUS_PAYMENT_FAILED = "PAYMENT_FAILED"
    STATUS_READY_FOR_PICKUP = "READY_FOR_PICKUP"
    STATUS_READY_FOR_DELIVERY = "READY_FOR_DELIVERY"
    STATUS_VEHICLE_ASSIGNED = "VEHICLE_ASSIGNED"
    STATUS_THIRD_PARTY_ASSIGNED = "THIRD_PARTY_ASSIGNED"
    STATUS_DISPATCHED = "DISPATCHED"
    STATUS_IN_TRANSIT = "IN_TRANSIT"
    STATUS_DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
    STATUS_COMPLETED_PICKUP = "COMPLETED_PICKUP"
    STATUS_COMPLETED_COMPANY = "COMPLETED_COMPANY"
    STATUS_COMPLETED_THIRD_PARTY = "COMPLETED_THIRD_PARTY"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_NEW_ORDER, "New Order"),
        (STATUS_STOCK_VERIFICATION, "Stock Verification"),
        (STATUS_OUT_OF_STOCK, "Out of Stock"),
        (STATUS_PENDING_DELIVERY_COST, "Pending Delivery Cost"),
        (STATUS_DELIVERY_COST_CALC, "Delivery Cost Calculation"),
        (STATUS_QUOTATION_PREP, "Quotation Preparation"),
        (STATUS_QUOTATION_SENT, "Quotation Sent"),
        (STATUS_WAITING_CUSTOMER, "Waiting Customer Response"),
        (STATUS_QUOTATION_ACCEPTED, "Quotation Accepted"),
        (STATUS_QUOTATION_REJECTED, "Quotation Rejected"),
        (STATUS_INVOICE_GENERATED, "Invoice Generated"),
        (STATUS_AWAITING_PAYMENT, "Awaiting Payment"),
        (STATUS_PAYMENT_CONFIRMED, "Payment Confirmed"),
        (STATUS_PAYMENT_FAILED, "Payment Verification Failed"),
        (STATUS_READY_FOR_PICKUP, "Ready for Pickup"),
        (STATUS_READY_FOR_DELIVERY, "Ready for Delivery"),
        (STATUS_VEHICLE_ASSIGNED, "Vehicle Assigned"),
        (STATUS_THIRD_PARTY_ASSIGNED, "Third Party Assigned"),
        (STATUS_DISPATCHED, "Dispatched"),
        (STATUS_IN_TRANSIT, "In Transit"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_DELIVERY_CONFIRMED, "Delivery Confirmed"),
        (STATUS_COMPLETED_PICKUP, "Completed — Customer Pickup"),
        (STATUS_COMPLETED_COMPANY, "Completed — Company Delivery"),
        (STATUS_COMPLETED_THIRD_PARTY, "Completed — Third Party"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_DRAFT, "Draft"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PARTIAL, "Partial"),
    ]

    INV_NONE = "NONE"
    INV_RESERVED = "RESERVED"
    INV_LOCKED = "LOCKED"
    INV_RELEASED = "RELEASED"
    INVENTORY_STATUS_CHOICES = [
        (INV_NONE, "None"),
        (INV_RESERVED, "Reserved"),
        (INV_LOCKED, "Locked"),
        (INV_RELEASED, "Released"),
    ]

    METHOD_PICKUP = "PICKUP"
    METHOD_COMPANY = "COMPANY"
    METHOD_THIRD_PARTY = "THIRD_PARTY"
    DELIVERY_METHOD_CHOICES = [
        (METHOD_PICKUP, "Customer Pickup"),
        (METHOD_COMPANY, "Company Delivery"),
        (METHOD_THIRD_PARTY, "Third Party Transport"),
    ]

    DELIVERY_PENDING = "PENDING"
    DELIVERY_PROCESSING = "PROCESSING"
    DELIVERY_PARTIAL = "PARTIAL"
    DELIVERY_DELIVERED = "DELIVERED"
    DELIVERY_CANCELLED = "CANCELLED"
    DELIVERY_STATUS_CHOICES = [
        (DELIVERY_PENDING, "Pending"),
        (DELIVERY_PROCESSING, "Processing"),
        (DELIVERY_PARTIAL, "Partial"),
        (DELIVERY_DELIVERED, "Delivered"),
        (DELIVERY_CANCELLED, "Cancelled"),
    ]

    PAYMENT_UNPAID = "UNPAID"
    PAYMENT_PARTIAL = "PARTIAL"
    PAYMENT_PAID = "PAID"
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_UNPAID, "Unpaid"),
        (PAYMENT_PARTIAL, "Partial"),
        (PAYMENT_PAID, "Paid"),
    ]

    so_number = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    quotation = models.ForeignKey(
        SalesQuotation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders",
    )
    lpo_number = models.CharField(max_length=100, blank=True)
    lpo_date = models.DateField(null=True, blank=True)
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    delivery_date = models.DateField()
    delivery_address = models.TextField(blank=True)
    requested_delivery_location = models.TextField(blank=True)
    fulfillment_warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_orders",
    )
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_NEW_ORDER)
    inventory_status = models.CharField(
        max_length=20,
        choices=INVENTORY_STATUS_CHOICES,
        default=INV_NONE,
    )
    delivery_method = models.CharField(
        max_length=20,
        choices=DELIVERY_METHOD_CHOICES,
        blank=True,
    )
    delivery_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    linked_pr = models.ForeignKey(
        "procurement.PurchaseRequisition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders",
    )
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default=DELIVERY_PENDING,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_UNPAID,
    )
    apply_vat = models.BooleanField(default=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_orders_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.so_number


class SalesOrderItem(models.Model):
    """Line item on a sales order."""

    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="sales_order_lines",
    )
    quantity_ordered = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    quantity_delivered = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    quantity_reserved = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    stock_available_snapshot = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
    )
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["id"]


class SalesOrderActivity(models.Model):
    """Audit trail for sales order actions."""

    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    action = models.CharField(max_length=100)
    previous_status = models.CharField(max_length=40, blank=True)
    new_status = models.CharField(max_length=40, blank=True)
    details = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sales_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class SalesOrderDeliveryCost(BaseModel):
    """Logistics delivery cost breakdown for a sales order."""

    TRANSPORT_ROAD = "ROAD"
    TRANSPORT_RAIL = "RAIL"
    TRANSPORT_AIR = "AIR"
    TRANSPORT_CHOICES = [
        (TRANSPORT_ROAD, "Road"),
        (TRANSPORT_RAIL, "Rail"),
        (TRANSPORT_AIR, "Air"),
    ]

    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="delivery_cost_detail",
    )
    delivery_distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
    )
    transport_method = models.CharField(
        max_length=20,
        choices=TRANSPORT_CHOICES,
        default=TRANSPORT_ROAD,
    )
    vehicle_type = models.CharField(max_length=50, blank=True)
    fuel_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    loading_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    offloading_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    additional_charges = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total_delivery_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_costs_calculated",
    )
    notes = models.TextField(blank=True)

    def recalculate_total(self):
        self.total_delivery_cost = (
            self.fuel_cost
            + self.loading_cost
            + self.offloading_cost
            + self.additional_charges
        )
        return self.total_delivery_cost


class SalesOrderPaymentProof(BaseModel):
    """Customer payment submission pending finance verification."""

    STATUS_PENDING = "PENDING"
    STATUS_VERIFIED = "VERIFIED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_FAILED, "Failed"),
    ]

    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="payment_proofs",
    )
    METHOD_CASH = "CASH"
    METHOD_BANK = "BANK_TRANSFER"
    METHOD_CHEQUE = "CHEQUE"
    METHOD_MOBILE = "MOBILE"
    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_BANK, "Bank Transfer"),
        (METHOD_CHEQUE, "Cheque"),
        (METHOD_MOBILE, "Mobile Money"),
    ]

    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference_number = models.CharField(max_length=100)
    proof_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_proofs_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_proofs_submitted",
    )


class SalesOrderPickupDetail(BaseModel):
    """Customer pickup confirmation."""

    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="pickup_detail",
    )
    pickup_date = models.DateField()
    receiver_name = models.CharField(max_length=150)
    receiver_phone = models.CharField(max_length=30)
    signature_data = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pickups_recorded",
    )


class SalesOrderDispatchAssignment(BaseModel):
    """Vehicle or third-party transport assignment."""

    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="dispatch_assignment",
    )
    assignment_type = models.CharField(max_length=20, choices=SalesOrder.DELIVERY_METHOD_CHOICES)
    vehicle = models.ForeignKey(
        "logistics.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="so_assignments",
    )
    driver = models.ForeignKey(
        "logistics.Driver",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="so_assignments",
    )
    driver_phone = models.CharField(max_length=30, blank=True)
    dispatch_date = models.DateField(null=True, blank=True)
    transport_company = models.CharField(max_length=255, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispatch_assignments",
    )


class SalesInvoice(BaseModel):
    """Tax invoice — TRA compliant."""

    STATUS_DRAFT = "DRAFT"
    STATUS_SENT = "SENT"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_PAID = "PAID"
    STATUS_OVERDUE = "OVERDUE"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_PAID, "Paid"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="sales_invoices",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    delivery_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    tra_receipt_number = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_invoices",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.invoice_number

    @property
    def balance(self):
        return self.total_amount - self.paid_amount


class SalesInvoiceItem(models.Model):
    """Line item on a sales invoice."""

    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("18"),
    )
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["id"]


class CustomerPayment(BaseModel):
    """Customer payment receipt."""

    METHOD_CASH = "CASH"
    METHOD_BANK = "BANK_TRANSFER"
    METHOD_CHEQUE = "CHEQUE"
    METHOD_MOBILE = "MOBILE"
    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_BANK, "Bank Transfer"),
        (METHOD_CHEQUE, "Cheque"),
        (METHOD_MOBILE, "Mobile Money"),
    ]

    payment_number = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="customer_payments",
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments_received",
    )

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return self.payment_number


class CreditNote(BaseModel):
    """Credit note against an invoice."""

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVED = "APPROVED"
    STATUS_APPLIED = "APPLIED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_APPLIED, "Applied"),
    ]

    cn_number = models.CharField(max_length=30, unique=True, editable=False)
    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        related_name="credit_notes",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="credit_notes",
    )
    reason = models.TextField()
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="credit_notes_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_notes_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.cn_number
