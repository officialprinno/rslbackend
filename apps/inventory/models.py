"""
Inventory models for Rock Solutions FMS.

Shared inventory across departments: items, warehouses, stock levels,
movements, adjustments, serial numbers, and alerts.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class ItemCategory(BaseModel):
    """Hierarchical item category (Rock Drilling Tools, Wire Mesh, etc.)."""

    code = models.CharField(max_length=10, unique=True, blank=True, default="")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        verbose_name_plural = "item categories"
        ordering = ["name"]
        unique_together = [("name", "parent")]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name


class Item(BaseModel):
    """Inventory item — traded goods, manufactured products, or raw materials."""

    ITEM_TYPE_TRADED = "TRADED"
    ITEM_TYPE_RAW_MATERIAL = "RAW_MATERIAL"
    ITEM_TYPE_WORK_IN_PROGRESS = "WORK_IN_PROGRESS"
    ITEM_TYPE_FINISHED_GOODS = "FINISHED_GOODS"
    ITEM_TYPE_MANUFACTURED = "MANUFACTURED"
    ITEM_TYPE_PPE = "PPE"
    ITEM_TYPE_SPARE_PART = "SPARE_PART"
    ITEM_TYPE_ASSET = "ASSET"
    ITEM_TYPE_SERVICE = "SERVICE"

    ITEM_TYPE_CHOICES = [
        (ITEM_TYPE_TRADED, "Traded"),
        (ITEM_TYPE_RAW_MATERIAL, "Raw Material"),
        (ITEM_TYPE_WORK_IN_PROGRESS, "Work in Progress"),
        (ITEM_TYPE_FINISHED_GOODS, "Finished Goods"),
        (ITEM_TYPE_MANUFACTURED, "Manufactured"),
        (ITEM_TYPE_PPE, "PPE"),
        (ITEM_TYPE_SPARE_PART, "Spare Part"),
        (ITEM_TYPE_ASSET, "Asset"),
        (ITEM_TYPE_SERVICE, "Service"),
    ]

    USAGE_FOR_SALE = "FOR_SALE"
    USAGE_INTERNAL = "INTERNAL_USE"
    USAGE_BOTH = "BOTH"
    ITEM_USAGE_CHOICES = [
        (USAGE_FOR_SALE, "For Sale"),
        (USAGE_INTERNAL, "Internal Use"),
        (USAGE_BOTH, "Both"),
    ]

    NON_STOCK_ITEM_TYPES = frozenset({ITEM_TYPE_SERVICE})

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    subcategory = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ItemCategory,
        on_delete=models.PROTECT,
        related_name="items",
    )
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    item_usage = models.CharField(
        max_length=20,
        choices=ITEM_USAGE_CHOICES,
        default=USAGE_BOTH,
        help_text="Commercial sales, internal consumption, or both.",
    )
    unit_of_measure = models.CharField(max_length=50)
    has_serial_number = models.BooleanField(default=False)
    has_batch_tracking = models.BooleanField(default=False)
    has_expiry_date = models.BooleanField(default=False)
    reorder_level = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    minimum_stock = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    maximum_stock = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    safety_stock = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    lead_time_days = models.PositiveIntegerField(default=0)
    preferred_supplier = models.ForeignKey(
        "procurement.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preferred_items",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="items",
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    selling_price = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def tracks_stock(self) -> bool:
        """Non-stock services do not participate in quantity tracking."""
        return self.item_type not in self.NON_STOCK_ITEM_TYPES


class Warehouse(BaseModel):
    """Physical storage location (Main Warehouse, Factory Store, etc.)."""

    TYPE_RAW_MATERIAL = "RAW_MATERIAL"
    TYPE_FINISHED_GOODS = "FINISHED_GOODS"
    TYPE_MINING_CONSUMABLES = "MINING_CONSUMABLES"
    TYPE_PPE = "PPE"
    TYPE_SPARE_PARTS = "SPARE_PARTS"
    TYPE_TRANSIT = "TRANSIT"

    WAREHOUSE_TYPE_CHOICES = [
        (TYPE_RAW_MATERIAL, "Raw Material Warehouse"),
        (TYPE_FINISHED_GOODS, "Finished Goods Warehouse"),
        (TYPE_MINING_CONSUMABLES, "Mining Consumables Warehouse"),
        (TYPE_PPE, "PPE Warehouse"),
        (TYPE_SPARE_PARTS, "Spare Parts Warehouse"),
        (TYPE_TRANSIT, "Transit Warehouse"),
    ]

    name = models.CharField(max_length=150, unique=True)
    location = models.CharField(max_length=255, blank=True)
    warehouse_type = models.CharField(
        max_length=30,
        choices=WAREHOUSE_TYPE_CHOICES,
        default=TYPE_MINING_CONSUMABLES,
    )
    capacity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_warehouses",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Stock(models.Model):
    """Current stock level per item per warehouse."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stock_levels")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    quantity_on_hand = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity_reserved = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity_available = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("item", "warehouse")]
        ordering = ["warehouse", "item"]
        verbose_name_plural = "stock"

    def __str__(self):
        return f"{self.item.code} @ {self.warehouse.name}: {self.quantity_on_hand}"

    def recalculate_available(self):
        """Recompute available quantity from on-hand minus reserved."""
        self.quantity_available = self.quantity_on_hand - self.quantity_reserved

    def save(self, *args, **kwargs):
        self.recalculate_available()
        super().save(*args, **kwargs)


class StockMovement(models.Model):
    """Immutable log of every stock quantity change."""

    MOVEMENT_IN = "IN"
    MOVEMENT_OUT = "OUT"
    MOVEMENT_TRANSFER = "TRANSFER"
    MOVEMENT_ADJUSTMENT = "ADJUSTMENT"
    MOVEMENT_PRODUCTION_CONSUMPTION = "PRODUCTION_CONSUMPTION"
    MOVEMENT_PRODUCTION_OUTPUT = "PRODUCTION_OUTPUT"

    MOVEMENT_TYPE_CHOICES = [
        (MOVEMENT_IN, "In"),
        (MOVEMENT_OUT, "Out"),
        (MOVEMENT_TRANSFER, "Transfer"),
        (MOVEMENT_ADJUSTMENT, "Adjustment"),
        (MOVEMENT_PRODUCTION_CONSUMPTION, "Production Consumption"),
        (MOVEMENT_PRODUCTION_OUTPUT, "Production Output"),
    ]

    REFERENCE_GRN = "GRN"
    REFERENCE_GIN = "GIN"
    REFERENCE_DEPT_REQUEST = "DEPT_REQUEST"
    REFERENCE_SALES_ORDER = "SALES_ORDER"
    REFERENCE_WORK_ORDER = "WORK_ORDER"
    REFERENCE_TRANSFER = "TRANSFER"
    REFERENCE_ADJUSTMENT = "ADJUSTMENT"
    REFERENCE_MANUAL = "MANUAL"

    REFERENCE_TYPE_CHOICES = [
        (REFERENCE_GRN, "GRN"),
        (REFERENCE_GIN, "GIN"),
        (REFERENCE_DEPT_REQUEST, "Department Request"),
        (REFERENCE_SALES_ORDER, "Sales Order"),
        (REFERENCE_WORK_ORDER, "Work Order"),
        (REFERENCE_TRANSFER, "Transfer"),
        (REFERENCE_ADJUSTMENT, "Adjustment"),
        (REFERENCE_MANUAL, "Manual"),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=30, choices=MOVEMENT_TYPE_CHOICES)
    reference_type = models.CharField(max_length=30, choices=REFERENCE_TYPE_CHOICES)
    reference_id = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    serial_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} {self.item.code} ({self.created_at:%Y-%m-%d})"


class StockAdjustment(BaseModel):
    """Stock increase/decrease request requiring approval."""

    ADJUSTMENT_INCREASE = "INCREASE"
    ADJUSTMENT_DECREASE = "DECREASE"
    ADJUSTMENT_DAMAGE = "DAMAGE"
    ADJUSTMENT_LOSS = "LOSS"
    ADJUSTMENT_WRITE_OFF = "WRITE_OFF"
    ADJUSTMENT_PHYSICAL_COUNT = "PHYSICAL_COUNT"

    ADJUSTMENT_TYPE_CHOICES = [
        (ADJUSTMENT_INCREASE, "Increase"),
        (ADJUSTMENT_DECREASE, "Decrease"),
        (ADJUSTMENT_DAMAGE, "Damage"),
        (ADJUSTMENT_LOSS, "Loss"),
        (ADJUSTMENT_WRITE_OFF, "Write Off"),
        (ADJUSTMENT_PHYSICAL_COUNT, "Physical Count Difference"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="adjustments")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="adjustments",
    )
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_adjustments_requested",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_adjustments_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.adjustment_type} {self.quantity} {self.item.code} [{self.status}]"


class ItemSerialNumber(BaseModel):
    """Tracked serial number for equipment items."""

    STATUS_IN_STOCK = "IN_STOCK"
    STATUS_SOLD = "SOLD"
    STATUS_RESERVED = "RESERVED"
    STATUS_DAMAGED = "DAMAGED"

    STATUS_CHOICES = [
        (STATUS_IN_STOCK, "In Stock"),
        (STATUS_SOLD, "Sold"),
        (STATUS_RESERVED, "Reserved"),
        (STATUS_DAMAGED, "Damaged"),
    ]

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="serial_numbers")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="serial_numbers",
    )
    serial_number = models.CharField(max_length=100)
    manufacturer_serial = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_STOCK)
    sold_to = models.ForeignKey(
        "sales.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchased_serials",
    )

    class Meta:
        ordering = ["serial_number"]
        unique_together = [("item", "serial_number")]

    def __str__(self):
        return f"{self.serial_number} ({self.item.code})"


class StockAlert(models.Model):
    """Automated alert for low stock, out of stock, or approaching expiry."""

    ALERT_LOW_STOCK = "LOW_STOCK"
    ALERT_OUT_OF_STOCK = "OUT_OF_STOCK"
    ALERT_EXPIRY_SOON = "EXPIRY_SOON"
    ALERT_OVERSTOCK = "OVERSTOCK"
    ALERT_NEGATIVE_STOCK = "NEGATIVE_STOCK"
    ALERT_PENDING_APPROVAL = "PENDING_APPROVAL"

    ALERT_TYPE_CHOICES = [
        (ALERT_LOW_STOCK, "Low Stock"),
        (ALERT_OUT_OF_STOCK, "Out of Stock"),
        (ALERT_EXPIRY_SOON, "Expiry Soon"),
        (ALERT_OVERSTOCK, "Overstock"),
        (ALERT_NEGATIVE_STOCK, "Negative Stock"),
        (ALERT_PENDING_APPROVAL, "Pending Approval"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="alerts")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_read", "alert_type"]),
        ]

    def __str__(self):
        return f"{self.alert_type}: {self.item.code} @ {self.warehouse.name}"


class StockBatch(BaseModel):
    """Batch/lot tracking for consumables, PPE, and chemicals."""

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="batches")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=100)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    supplier = models.ForeignKey(
        "procurement.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_batches",
    )
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("item", "warehouse", "batch_number")]

    def __str__(self):
        return f"{self.batch_number} — {self.item.code}"


class StockTransfer(BaseModel):
    """Inter-warehouse stock transfer with approval workflow."""

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    transfer_number = models.CharField(max_length=30, unique=True, editable=False)
    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_transfers_requested",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transfers_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.transfer_number


class StockTransferLine(models.Model):
    """Line item on a stock transfer."""

    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="transfer_lines")
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )

    class Meta:
        ordering = ["id"]


class DepartmentRequest(BaseModel):
    """Department stock requisition workflow."""

    DEPT_PRODUCTION = "PRODUCTION"
    DEPT_PROCUREMENT = "PROCUREMENT"
    DEPT_HSE = "HSE"
    DEPT_LOGISTICS = "LOGISTICS"
    DEPT_MAINTENANCE = "MAINTENANCE"
    DEPT_ADMINISTRATION = "ADMINISTRATION"

    DEPARTMENT_CHOICES = [
        (DEPT_PRODUCTION, "Production"),
        (DEPT_PROCUREMENT, "Procurement"),
        (DEPT_HSE, "HSE"),
        (DEPT_LOGISTICS, "Logistics"),
        (DEPT_MAINTENANCE, "Maintenance"),
        (DEPT_ADMINISTRATION, "Administration"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_APPROVED = "APPROVED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_ISSUED = "ISSUED"
    STATUS_PARTIALLY_ISSUED = "PARTIALLY_ISSUED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_PARTIALLY_ISSUED, "Partially Issued"),
        (STATUS_REJECTED, "Rejected"),
    ]

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

    request_number = models.CharField(max_length=30, unique=True, editable=False)
    department = models.CharField(max_length=30, choices=DEPARTMENT_CHOICES)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="department_requests",
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
    )
    purpose = models.TextField(blank=True)
    needed_by_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="department_requests_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="department_requests_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    approval_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.request_number


class DepartmentRequestLine(models.Model):
    """Line item on a department request."""

    request = models.ForeignKey(
        DepartmentRequest,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="dept_request_lines")
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        help_text="Requested quantity (legacy field, mirrors requested_qty).",
    )
    requested_qty = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    issued_qty = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dept_request_lines",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.requested_qty is None:
            self.requested_qty = self.quantity
        else:
            self.quantity = self.requested_qty
        super().save(*args, **kwargs)

    @property
    def remaining_qty(self):
        requested = self.requested_qty or self.quantity
        return requested - (self.issued_qty or Decimal("0"))


class GoodsIssueNote(BaseModel):
    """Goods Issue Note — stock issued to departments or production."""

    DEPT_PRODUCTION = "PRODUCTION"
    DEPT_MAINTENANCE = "MAINTENANCE"
    DEPT_HSE = "HSE"
    DEPT_LOGISTICS = "LOGISTICS"
    DEPT_SALES = "SALES"
    DEPT_PROCUREMENT = "PROCUREMENT"
    DEPT_ADMINISTRATION = "ADMINISTRATION"

    DEPARTMENT_CHOICES = [
        (DEPT_PRODUCTION, "Production"),
        (DEPT_MAINTENANCE, "Maintenance"),
        (DEPT_HSE, "HSE"),
        (DEPT_LOGISTICS, "Logistics"),
        (DEPT_SALES, "Sales"),
        (DEPT_PROCUREMENT, "Procurement"),
        (DEPT_ADMINISTRATION, "Administration"),
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

    ISSUE_SALES = "SALES"
    ISSUE_INTERNAL = "INTERNAL"
    ISSUE_PRODUCTION = "PRODUCTION"
    ISSUE_TRANSFER = "TRANSFER"
    ISSUE_TYPE_CHOICES = [
        (ISSUE_SALES, "Sales"),
        (ISSUE_INTERNAL, "Internal"),
        (ISSUE_PRODUCTION, "Production"),
        (ISSUE_TRANSFER, "Transfer"),
    ]

    gin_number = models.CharField(max_length=30, unique=True, editable=False)
    issue_type = models.CharField(
        max_length=20,
        choices=ISSUE_TYPE_CHOICES,
        default=ISSUE_INTERNAL,
    )
    department = models.CharField(max_length=30, choices=DEPARTMENT_CHOICES)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="goods_issue_notes",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reason = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="gins_requested",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gins_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    department_request = models.ForeignKey(
        DepartmentRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goods_issue_notes",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.gin_number


class GoodsIssueLine(models.Model):
    """Line item on a goods issue note."""

    gin = models.ForeignKey(
        GoodsIssueNote,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="gin_lines")
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )

    class Meta:
        ordering = ["id"]


class StockTake(BaseModel):
    """Physical inventory count / stock take."""

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    take_number = models.CharField(max_length=30, unique=True, editable=False)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_takes",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    notes = models.TextField(blank=True)
    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_takes_conducted",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_takes_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.take_number


class StockTakeLine(models.Model):
    """Counted line on a stock take."""

    stock_take = models.ForeignKey(
        StockTake,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_take_lines")
    system_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    physical_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    variance = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.variance = self.physical_quantity - self.system_quantity
        super().save(*args, **kwargs)
