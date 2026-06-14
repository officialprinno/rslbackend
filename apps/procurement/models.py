"""
Procurement models for Rock Solutions FMS.

Suppliers → PR → RFQ → Quotations → PO → GRN → Supplier Invoices
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Supplier(BaseModel):
    """Registered supplier / vendor."""

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

    name = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=100, blank=True)
    tin_number = models.CharField(max_length=50)
    vat_number = models.CharField(max_length=50, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Tanzania")
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="suppliers",
    )
    payment_terms = models.CharField(
        max_length=20,
        choices=PAYMENT_TERMS_CHOICES,
        default=PAYMENT_NET_30,
    )
    rating = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseRequisition(BaseModel):
    """Internal purchase request."""

    PRIORITY_LOW = "LOW"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_URGENT = "URGENT"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    pr_number = models.CharField(max_length=30, unique=True, editable=False)
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.PROTECT,
        related_name="purchase_requisitions",
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    notes = models.TextField(blank=True)
    total_estimated = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_requisitions",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_requisitions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.pr_number


class PurchaseRequisitionItem(BaseModel):
    """Line item on a purchase requisition."""

    requisition = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="requisition_lines",
    )
    quantity_requested = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit_cost_estimate = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    total_estimate = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.total_estimate = self.quantity_requested * self.unit_cost_estimate
        super().save(*args, **kwargs)


class RequestForQuotation(BaseModel):
    """RFQ sent to suppliers for an approved PR."""

    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    rfq_number = models.CharField(max_length=30, unique=True, editable=False)
    requisition = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.PROTECT,
        related_name="rfqs",
    )
    deadline = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_rfqs",
    )
    suppliers = models.ManyToManyField(
        Supplier,
        through="RFQSupplier",
        related_name="rfqs",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.rfq_number


class RFQSupplier(BaseModel):
    """Supplier invited to respond to an RFQ."""

    rfq = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("rfq", "supplier")]


class SupplierQuotation(BaseModel):
    """Supplier response to an RFQ."""

    STATUS_PENDING = "PENDING"
    STATUS_SELECTED = "SELECTED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SELECTED, "Selected"),
        (STATUS_REJECTED, "Rejected"),
    ]

    quotation_number = models.CharField(max_length=50)
    rfq = models.ForeignKey(
        RequestForQuotation,
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    quotation_date = models.DateField()
    valid_until = models.DateField()
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    delivery_days = models.PositiveIntegerField(default=7)
    total_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-quotation_date"]
        unique_together = [("rfq", "supplier")]

    def __str__(self):
        return self.quotation_number


class SupplierQuotationItem(BaseModel):
    """Quoted line item."""

    quotation = models.ForeignKey(
        SupplierQuotation,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="quotation_lines",
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class PurchaseOrder(BaseModel):
    """Purchase order to a supplier."""

    STATUS_DRAFT = "DRAFT"
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_SENT = "SENT"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_RECEIVED = "RECEIVED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_SENT, "Sent"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    po_number = models.CharField(max_length=30, unique=True, editable=False)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    quotation = models.ForeignKey(
        SupplierQuotation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders",
    )
    requisition = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    order_date = models.DateField()
    expected_delivery = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(
        max_length=20,
        choices=Supplier.PAYMENT_TERMS_CHOICES,
        default=Supplier.PAYMENT_NET_30,
    )
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    apply_vat = models.BooleanField(default=True)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_purchase_orders",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_purchase_orders",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.po_number


class PurchaseOrderItem(BaseModel):
    """PO line item."""

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="po_lines",
    )
    quantity_ordered = models.DecimalField(max_digits=18, decimal_places=4)
    quantity_received = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
    )
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    def save(self, *args, **kwargs):
        gross = self.quantity_ordered * self.unit_price
        discount = gross * (self.discount_percent / Decimal("100"))
        self.total_price = gross - discount
        super().save(*args, **kwargs)


class GoodsReceivedNote(BaseModel):
    """Goods received against a purchase order."""

    STATUS_DRAFT = "DRAFT"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_POSTED = "POSTED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_POSTED, "Posted"),
    ]

    grn_number = models.CharField(max_length=30, unique=True, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="grns",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.PROTECT,
        related_name="grns",
    )
    received_date = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_grns",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.grn_number


class GRNItem(BaseModel):
    """GRN line — quantity received now."""

    CONDITION_GOOD = "GOOD"
    CONDITION_DAMAGED = "DAMAGED"
    CONDITION_REJECTED = "REJECTED"
    CONDITION_CHOICES = [
        (CONDITION_GOOD, "Good"),
        (CONDITION_DAMAGED, "Damaged"),
        (CONDITION_REJECTED, "Rejected"),
    ]

    grn = models.ForeignKey(
        GoodsReceivedNote,
        on_delete=models.CASCADE,
        related_name="items",
    )
    po_item = models.ForeignKey(
        PurchaseOrderItem,
        on_delete=models.PROTECT,
        related_name="grn_lines",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="grn_lines",
    )
    quantity_received = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    serial_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default=CONDITION_GOOD,
    )
    notes = models.TextField(blank=True)


class SupplierInvoice(BaseModel):
    """Supplier invoice with 3-way matching."""

    STATUS_PENDING = "PENDING"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_PAID = "PAID"
    STATUS_OVERDUE = "OVERDUE"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_PAID, "Paid"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    invoice_number = models.CharField(max_length=50)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    grn = models.ForeignKey(
        GoodsReceivedNote,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    invoice_date = models.DateField()
    due_date = models.DateField()
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="supplier_invoices",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    three_way_matched = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-invoice_date"]
        unique_together = [("supplier", "invoice_number")]

    @property
    def balance(self):
        return self.total_amount - self.paid_amount


class InvoicePayment(BaseModel):
    """Payment recorded against a supplier invoice."""

    invoice = models.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50)
    reference = models.CharField(max_length=100, blank=True)
    bank = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoice_payments",
    )
