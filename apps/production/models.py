"""
Production models for Rock Solutions FMS.

Wire Mesh manufacturing: Products → BOM → Work Orders → Output → Inventory
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Product(BaseModel):
    """Manufactured wire mesh product catalogue entry."""

    item = models.OneToOneField(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="production_product",
    )
    name = models.CharField(max_length=255)
    specifications = models.JSONField(default=dict, blank=True)
    standard_output = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit_of_measure = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BillOfMaterials(BaseModel):
    """Raw material recipe for a product."""

    STATUS_DRAFT = "DRAFT"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_INACTIVE = "INACTIVE"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="boms",
    )
    version = models.CharField(max_length=20, default="1.0")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    material_cost_per_unit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="boms_created",
    )

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["product", "version"]]

    def __str__(self):
        return f"{self.product.name} BOM v{self.version}"


class BOMItem(models.Model):
    """Component line on a bill of materials."""

    bom = models.ForeignKey(
        BillOfMaterials,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="production_bom_components",
    )
    quantity_required = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    wastage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    @property
    def effective_quantity(self):
        return self.quantity_required * (1 + self.wastage_percent / Decimal("100"))


class Machine(BaseModel):
    """Production equipment."""

    TYPE_WIRE_DRAWING = "WIRE_DRAWING"
    TYPE_MESH_WEAVING = "MESH_WEAVING"
    TYPE_CUTTING = "CUTTING"
    TYPE_OTHER = "OTHER"
    TYPE_CHOICES = [
        (TYPE_WIRE_DRAWING, "Wire Drawing Machine"),
        (TYPE_MESH_WEAVING, "Mesh Weaving Machine"),
        (TYPE_CUTTING, "Cutting Machine"),
        (TYPE_OTHER, "Other"),
    ]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_MAINTENANCE = "MAINTENANCE"
    STATUS_BREAKDOWN = "BREAKDOWN"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_MAINTENANCE, "Maintenance"),
        (STATUS_BREAKDOWN, "Breakdown"),
    ]

    RUNTIME_RUNNING = "RUNNING"
    RUNTIME_IDLE = "IDLE"
    RUNTIME_MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"
    RUNTIME_BREAKDOWN = "BREAKDOWN"
    RUNTIME_CHOICES = [
        (RUNTIME_RUNNING, "Running"),
        (RUNTIME_IDLE, "Idle"),
        (RUNTIME_MAINTENANCE_REQUIRED, "Maintenance Required"),
        (RUNTIME_BREAKDOWN, "Breakdown"),
    ]

    machine_code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=255)
    machine_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_MESH_WEAVING)
    purchase_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    last_service_date = models.DateField(null=True, blank=True)
    next_service_date = models.DateField(null=True, blank=True)
    runtime_condition = models.CharField(
        max_length=30,
        choices=RUNTIME_CHOICES,
        default=RUNTIME_IDLE,
        blank=True,
    )
    runtime_notes = models.TextField(blank=True)
    runtime_updated_at = models.DateTimeField(null=True, blank=True)
    runtime_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="machine_runtime_updates",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["machine_code"]

    def __str__(self):
        return f"{self.machine_code} — {self.name}"


class MachineBreakdownRecord(BaseModel):
    """Operator-reported machine breakdown with optional photo evidence."""

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="breakdown_records",
    )
    work_order = models.ForeignKey(
        "WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="machine_breakdowns",
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="machine_breakdowns_reported",
    )
    notes = models.TextField()
    photo = models.ImageField(upload_to="production/breakdowns/", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Breakdown — {self.machine.machine_code}"


class MachineServiceRecord(BaseModel):
    """Machine maintenance / service history."""

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="service_records",
    )
    service_date = models.DateField()
    description = models.TextField()
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    performed_by = models.CharField(max_length=150, blank=True)
    next_service_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-service_date"]


class WorkOrder(BaseModel):
    """Production work order / job card."""

    SHIFT_MORNING = "MORNING"
    SHIFT_AFTERNOON = "AFTERNOON"
    SHIFT_NIGHT = "NIGHT"
    SHIFT_CHOICES = [
        (SHIFT_MORNING, "Morning"),
        (SHIFT_AFTERNOON, "Afternoon"),
        (SHIFT_NIGHT, "Night"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVED = "APPROVED"
    STATUS_ASSIGNED = "ASSIGNED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_PAUSED = "PAUSED"
    STATUS_COMPLETED_PENDING = "COMPLETED_PENDING"
    STATUS_PROD_APPROVED = "PROD_APPROVED"
    STATUS_WAITING_STORE = "WAITING_STORE"
    STATUS_INV_RECEIVED = "INV_RECEIVED"
    STATUS_CLOSED = "CLOSED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ASSIGNED, "Assigned"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_COMPLETED_PENDING, "Pending Production Approval"),
        (STATUS_PROD_APPROVED, "Production Approved"),
        (STATUS_WAITING_STORE, "Waiting Store Receipt"),
        (STATUS_INV_RECEIVED, "Inventory Received"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
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

    wo_number = models.CharField(max_length=30, unique=True, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="work_orders",
    )
    bom = models.ForeignKey(
        BillOfMaterials,
        on_delete=models.PROTECT,
        related_name="work_orders",
    )
    sales_order = models.ForeignKey(
        "sales.SalesOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_work_orders",
    )
    machine = models.ForeignKey(
        Machine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_orders",
    )
    quantity_planned = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    quantity_produced = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    quantity_rejected = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    planned_start = models.DateTimeField()
    planned_end = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default=SHIFT_MORNING)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
    )
    production_line = models.CharField(max_length=100, blank=True)
    execution_workflow = models.BooleanField(
        default=True,
        help_text="When true, inventory moves only after production approval and store receipt.",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)
    machine_condition = models.CharField(max_length=30, blank=True)
    production_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_orders_production_approved",
    )
    production_approved_at = models.DateTimeField(null=True, blank=True)
    store_received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_orders_store_received",
    )
    store_received_at = models.DateTimeField(null=True, blank=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_orders_operated",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_orders_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_orders_created",
    )
    notes = models.TextField(blank=True)
    materials_issued = models.BooleanField(default=False)

    class Meta:
        ordering = ["-planned_start"]

    def __str__(self):
        return self.wo_number

    @property
    def is_execution_workflow(self) -> bool:
        return bool(self.execution_workflow)


class WorkOrderPendingMaterial(models.Model):
    """Operator-recorded material consumption — posted to inventory on production approval."""

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="pending_materials",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="production_pending_materials",
    )
    quantity_consumed = models.DecimalField(max_digits=18, decimal_places=4)
    waste_quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    posted = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="production_pending_materials_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class WorkOrderProgressEntry(models.Model):
    """Operator progress report during production execution."""

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="progress_entries",
    )
    quantity_produced = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    quantity_defective = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    progress_percent = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0"))
    machine_notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="production_progress_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class WorkOrderPauseRecord(models.Model):
    """Downtime / pause log for production execution."""

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="pause_records",
    )
    reason = models.TextField()
    paused_at = models.DateTimeField()
    resumed_at = models.DateTimeField(null=True, blank=True)
    downtime_minutes = models.DecimalField(max_digits=10, decimal_places=1, default=Decimal("0"))
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="production_pause_records",
    )

    class Meta:
        ordering = ["-paused_at"]


class WorkOrderExecutionEvent(models.Model):
    """Immutable timeline of operator / supervisor actions."""

    ACTION_START = "START"
    ACTION_PAUSE = "PAUSE"
    ACTION_RESUME = "RESUME"
    ACTION_PROGRESS = "PROGRESS"
    ACTION_CONSUMPTION = "CONSUMPTION"
    ACTION_SUBMIT = "SUBMIT_COMPLETION"
    ACTION_MACHINE_STATUS = "MACHINE_STATUS"
    ACTION_ASSIGN = "ASSIGN"
    ACTION_PROD_APPROVE = "PROD_APPROVE"
    ACTION_STORE_RECEIPT = "STORE_RECEIPT"
    ACTION_CHOICES = [
        (ACTION_START, "Start"),
        (ACTION_PAUSE, "Pause"),
        (ACTION_RESUME, "Resume"),
        (ACTION_PROGRESS, "Progress"),
        (ACTION_CONSUMPTION, "Consumption"),
        (ACTION_SUBMIT, "Submit Completion"),
        (ACTION_MACHINE_STATUS, "Machine Status"),
        (ACTION_ASSIGN, "Assign Operator"),
        (ACTION_PROD_APPROVE, "Production Approve"),
        (ACTION_STORE_RECEIPT, "Store Receipt"),
    ]

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="execution_events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="production_execution_events",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class FinishedGoodsReceipt(BaseModel):
    """Storekeeper confirmation before finished goods enter inventory."""

    work_order = models.OneToOneField(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="finished_goods_receipt",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.PROTECT,
        related_name="finished_goods_receipts",
    )
    quantity_received = models.DecimalField(max_digits=18, decimal_places=4)
    batch_number = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="finished_goods_receipts",
    )
    posted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"FG Receipt — {self.work_order.wo_number}"


class WorkOrderMaterialIssue(models.Model):
    """Materials deducted from inventory when production starts."""

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name="material_issues",
    )
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="production_material_issues",
    )
    quantity_issued = models.DecimalField(max_digits=18, decimal_places=4)
    quantity_returned = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    wastage = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))

    class Meta:
        ordering = ["id"]


class OutputRecord(BaseModel):
    """Daily production output / batch record."""

    QC_PASS = "PASS"
    QC_FAIL = "FAIL"
    QC_CHOICES = [
        (QC_PASS, "Pass"),
        (QC_FAIL, "Fail"),
    ]

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.PROTECT,
        related_name="output_records",
    )
    batch_number = models.CharField(max_length=30, unique=True, editable=False)
    date = models.DateField()
    shift = models.CharField(max_length=20, choices=WorkOrder.SHIFT_CHOICES)
    quantity_produced = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity_rejected = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0"),
    )
    rejection_reason = models.TextField(blank=True)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="output_records_operated",
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="output_records_supervised",
    )
    quality_checked = models.BooleanField(default=False)
    quality_checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="output_records_qc",
    )
    qc_result = models.CharField(max_length=10, choices=QC_CHOICES, blank=True)
    qc_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return self.batch_number


class MachineUsage(models.Model):
    """Machine usage log per work order session."""

    machine = models.ForeignKey(
        Machine,
        on_delete=models.PROTECT,
        related_name="usage_records",
    )
    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.PROTECT,
        related_name="machine_usage",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="machine_usage_records",
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    hours_used = models.DecimalField(max_digits=8, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_time"]
