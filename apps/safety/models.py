"""
Safety / HSE models for Rock Solutions FMS.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class SafetyIncident(BaseModel):
    """Safety incident report."""

    TYPE_ACCIDENT = "ACCIDENT"
    TYPE_NEAR_MISS = "NEAR_MISS"
    TYPE_DANGEROUS = "DANGEROUS_OCCURRENCE"
    TYPE_PROPERTY = "PROPERTY_DAMAGE"
    TYPE_ENVIRONMENTAL = "ENVIRONMENTAL"
    TYPE_CHOICES = [
        (TYPE_ACCIDENT, "Accident"),
        (TYPE_NEAR_MISS, "Near Miss"),
        (TYPE_DANGEROUS, "Dangerous Occurrence"),
        (TYPE_PROPERTY, "Property Damage"),
        (TYPE_ENVIRONMENTAL, "Environmental"),
    ]

    SEV_LOW = "LOW"
    SEV_MEDIUM = "MEDIUM"
    SEV_HIGH = "HIGH"
    SEV_CRITICAL = "CRITICAL"
    SEVERITY_CHOICES = [
        (SEV_LOW, "Low"),
        (SEV_MEDIUM, "Medium"),
        (SEV_HIGH, "High"),
        (SEV_CRITICAL, "Critical"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_OPEN = "OPEN"
    STATUS_INVESTIGATING = "INVESTIGATING"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_OPEN, "Open"),
        (STATUS_INVESTIGATING, "Investigating"),
        (STATUS_CLOSED, "Closed"),
    ]

    incident_number = models.CharField(max_length=30, unique=True, editable=False)
    incident_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    date_occurred = models.DateTimeField()
    location = models.CharField(max_length=100)
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="safety_incidents",
    )
    description = models.TextField()
    immediate_actions = models.TextField(blank=True)
    anyone_injured = models.BooleanField(default=False)
    injured_person = models.ForeignKey(
        "hr.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="injury_incidents",
    )
    injury_description = models.TextField(blank=True)
    body_parts = models.JSONField(default=list, blank=True)
    medical_treatment_required = models.BooleanField(default=False)
    hospitalized = models.BooleanField(default=False)
    first_aid_given = models.BooleanField(default=False)
    first_aid_provider = models.CharField(max_length=150, blank=True)
    photos = models.JSONField(default=list, blank=True)
    documents = models.JSONField(default=list, blank=True)
    cctv_reference = models.CharField(max_length=255, blank=True)
    immediate_cause = models.TextField(blank=True)
    contributing_factors = models.JSONField(default=list, blank=True)
    root_cause = models.TextField(blank=True)
    root_cause_categories = models.JSONField(default=list, blank=True)
    why_analysis = models.JSONField(default=list, blank=True)
    investigation_findings = models.TextField(blank=True)
    investigator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents_investigated",
    )
    investigated_at = models.DateTimeField(null=True, blank=True)
    lessons_learned = models.TextField(blank=True)
    prevention_measures = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incidents_reported",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents_closed",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date_occurred"]

    def __str__(self):
        return self.incident_number

    @property
    def days_open(self):
        if self.status == self.STATUS_CLOSED:
            return 0
        return (timezone.now().date() - self.date_occurred.date()).days


class IncidentWitness(BaseModel):
    incident = models.ForeignKey(
        SafetyIncident, on_delete=models.CASCADE, related_name="witnesses"
    )
    name = models.CharField(max_length=150)
    is_employee = models.BooleanField(default=False)
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.SET_NULL, null=True, blank=True
    )
    contact = models.CharField(max_length=100, blank=True)
    statement = models.TextField(blank=True)


class CorrectiveAction(BaseModel):
    PRIORITY_LOW = "LOW"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
    ]

    STATUS_OPEN = "OPEN"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_DONE = "DONE"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_DONE, "Done"),
    ]

    incident = models.ForeignKey(
        SafetyIncident,
        on_delete=models.CASCADE,
        related_name="corrective_actions",
        null=True,
        blank=True,
    )
    inspection = models.ForeignKey(
        "SafetyInspection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="corrective_actions",
    )
    action = models.TextField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corrective_actions_assigned",
    )
    due_date = models.DateField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)


class SafetyInspection(BaseModel):
    TYPE_DAILY = "DAILY"
    TYPE_WEEKLY = "WEEKLY"
    TYPE_MONTHLY = "MONTHLY"
    TYPE_SPECIAL = "SPECIAL"
    TYPE_REGULATORY = "REGULATORY"
    TYPE_CHOICES = [
        (TYPE_DAILY, "Daily"),
        (TYPE_WEEKLY, "Weekly"),
        (TYPE_MONTHLY, "Monthly"),
        (TYPE_SPECIAL, "Special"),
        (TYPE_REGULATORY, "Regulatory"),
    ]

    RESULT_PASS = "PASS"
    RESULT_FAIL = "FAIL"
    RESULT_CONDITIONAL = "CONDITIONAL"
    RESULT_CHOICES = [
        (RESULT_PASS, "Pass"),
        (RESULT_FAIL, "Fail"),
        (RESULT_CONDITIONAL, "Conditional"),
    ]

    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
    ]

    inspection_number = models.CharField(max_length=30, unique=True, editable=False)
    inspection_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    area = models.CharField(max_length=100)
    scheduled_date = models.DateTimeField()
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspections_conducted",
    )
    overall_result = models.CharField(
        max_length=20, choices=RESULT_CHOICES, blank=True, null=True
    )
    total_items = models.PositiveIntegerField(default=0)
    passed_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    next_inspection = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-scheduled_date"]


class InspectionChecklistItem(BaseModel):
    RESULT_PASS = "PASS"
    RESULT_FAIL = "FAIL"
    RESULT_NA = "NA"
    RESULT_CHOICES = [
        (RESULT_PASS, "Pass"),
        (RESULT_FAIL, "Fail"),
        (RESULT_NA, "N/A"),
    ]

    inspection = models.ForeignKey(
        SafetyInspection, on_delete=models.CASCADE, related_name="checklist_items"
    )
    section = models.CharField(max_length=100)
    checklist_item = models.CharField(max_length=255)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, blank=True, null=True)
    remarks = models.TextField(blank=True)
    photo_url = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["section", "id"]


class PPEItem(BaseModel):
    TYPE_HELMET = "HELMET"
    TYPE_GLOVES = "GLOVES"
    TYPE_BOOTS = "SAFETY_BOOTS"
    TYPE_VEST = "VEST"
    TYPE_GOGGLES = "GOGGLES"
    TYPE_EAR = "EAR_PROTECTION"
    TYPE_HARNESS = "HARNESS"
    TYPE_RESPIRATOR = "RESPIRATOR"
    TYPE_UNIFORM = "UNIFORM"
    TYPE_OTHER = "OTHER"
    TYPE_CHOICES = [
        (TYPE_HELMET, "Helmet"),
        (TYPE_GLOVES, "Gloves"),
        (TYPE_BOOTS, "Safety Boots"),
        (TYPE_VEST, "Vest"),
        (TYPE_GOGGLES, "Goggles"),
        (TYPE_EAR, "Ear Protection"),
        (TYPE_HARNESS, "Harness"),
        (TYPE_RESPIRATOR, "Respirator"),
        (TYPE_UNIFORM, "Uniform / Workwear"),
        (TYPE_OTHER, "Other"),
    ]

    ppe_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    name = models.CharField(max_length=150)
    safety_standard = models.CharField(max_length=100, blank=True)
    inventory_item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ppe_items",
    )
    total_issued = models.PositiveIntegerField(default=0)
    stock_on_hand = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)

    class Meta:
        ordering = ["ppe_type", "name"]


class PPEIssuance(BaseModel):
    COND_NEW = "NEW"
    COND_GOOD = "GOOD"
    COND_FAIR = "FAIR"
    COND_ISSUED_CHOICES = [
        (COND_NEW, "New"),
        (COND_GOOD, "Good"),
        (COND_FAIR, "Fair"),
    ]

    COND_RETURNED_GOOD = "GOOD"
    COND_DAMAGED = "DAMAGED"
    COND_LOST = "LOST"
    COND_RETURNED_CHOICES = [
        (COND_RETURNED_GOOD, "Good"),
        (COND_FAIR, "Fair"),
        (COND_DAMAGED, "Damaged"),
        (COND_LOST, "Lost"),
    ]

    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.PROTECT, related_name="ppe_issuances"
    )
    ppe_item = models.ForeignKey(
        PPEItem, on_delete=models.PROTECT, related_name="issuances"
    )
    quantity = models.PositiveIntegerField(default=1)
    issue_date = models.DateField(default=timezone.now)
    expected_return = models.DateField(null=True, blank=True)
    actual_return = models.DateField(null=True, blank=True)
    condition_issued = models.CharField(max_length=20, choices=COND_ISSUED_CHOICES, default=COND_NEW)
    condition_returned = models.CharField(
        max_length=20, choices=COND_RETURNED_CHOICES, blank=True, null=True
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ppe_issued",
    )
    notes = models.TextField(blank=True)
    ppe_request = models.ForeignKey(
        "PPERequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issuances",
    )

    class Meta:
        ordering = ["-issue_date"]


class PPERequest(BaseModel):
    """PPE requisition workflow: Safety Officer → Store → Procurement → Issue."""

    STATUS_DRAFT = "DRAFT"
    STATUS_PENDING_STORE = "PENDING_STORE"
    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_IN_PROCUREMENT = "IN_PROCUREMENT"
    STATUS_STOCK_RECEIVED = "STOCK_RECEIVED"
    STATUS_READY_FOR_ISSUE = "READY_FOR_ISSUE"
    STATUS_ISSUED = "ISSUED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING_STORE, "Pending Store Review"),
        (STATUS_AVAILABLE, "Stock Available"),
        (STATUS_IN_PROCUREMENT, "In Procurement"),
        (STATUS_STOCK_RECEIVED, "Stock Received"),
        (STATUS_READY_FOR_ISSUE, "Ready for Issue"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    PRIORITY_NORMAL = "NORMAL"
    PRIORITY_URGENT = "URGENT"
    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    request_number = models.CharField(max_length=30, unique=True, editable=False)
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.PROTECT, related_name="ppe_requests"
    )
    ppe_item = models.ForeignKey(
        PPEItem, on_delete=models.PROTECT, related_name="requests"
    )
    quantity = models.PositiveIntegerField(default=1)
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL
    )
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ppe_requests_created",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    store_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ppe_requests_store_reviewed",
    )
    store_reviewed_at = models.DateTimeField(null=True, blank=True)
    store_notes = models.TextField(blank=True)
    stock_available = models.BooleanField(null=True, blank=True)
    purchase_requisition = models.ForeignKey(
        "procurement.PurchaseRequisition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ppe_requests",
    )
    procurement_notes = models.TextField(blank=True)
    stock_received_at = models.DateTimeField(null=True, blank=True)
    stock_received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ppe_requests_stock_received",
    )
    ready_at = models.DateTimeField(null=True, blank=True)
    issuance = models.ForeignKey(
        PPEIssuance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_request",
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    requested_new_item = models.BooleanField(
        default=False,
        help_text="True when Safety Officer requested an item not previously in stock",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.request_number


class PPERoleRequirement(BaseModel):
    job_title = models.CharField(max_length=150)
    required_ppe_types = models.JSONField(default=list)

    class Meta:
        ordering = ["job_title"]


class WorkPermit(BaseModel):
    TYPE_HOT = "HOT_WORK"
    TYPE_CONFINED = "CONFINED_SPACE"
    TYPE_ELECTRICAL = "ELECTRICAL"
    TYPE_HEIGHT = "HEIGHT_WORK"
    TYPE_EXCAVATION = "EXCAVATION"
    TYPE_CHEMICAL = "CHEMICAL"
    TYPE_GENERAL = "GENERAL"
    TYPE_CHOICES = [
        (TYPE_HOT, "Hot Work"),
        (TYPE_CONFINED, "Confined Space"),
        (TYPE_ELECTRICAL, "Electrical"),
        (TYPE_HEIGHT, "Height Work"),
        (TYPE_EXCAVATION, "Excavation"),
        (TYPE_CHEMICAL, "Chemical"),
        (TYPE_GENERAL, "General"),
    ]

    RISK_LOW = "LOW"
    RISK_MEDIUM = "MEDIUM"
    RISK_HIGH = "HIGH"
    RISK_CHOICES = [
        (RISK_LOW, "Low"),
        (RISK_MEDIUM, "Medium"),
        (RISK_HIGH, "High"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    permit_number = models.CharField(max_length=30, unique=True, editable=False)
    permit_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    work_description = models.TextField()
    location = models.CharField(max_length=100)
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_permits",
    )
    workers = models.JSONField(default=list, blank=True)
    equipment_tools = models.TextField(blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    hazards = models.JSONField(default=list, blank=True)
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default=RISK_MEDIUM)
    control_measures = models.TextField()
    safety_checklist = models.JSONField(default=list, blank=True)
    extension_count = models.PositiveSmallIntegerField(default=0)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="permits_issued",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permits_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-valid_from"]


class SafetyTraining(BaseModel):
    TYPE_INDUCTION = "INDUCTION"
    TYPE_REFRESHER = "REFRESHER"
    TYPE_SPECIFIC = "SPECIFIC"
    TYPE_EMERGENCY = "EMERGENCY"
    TYPE_REGULATORY = "REGULATORY"
    TYPE_CHOICES = [
        (TYPE_INDUCTION, "Induction"),
        (TYPE_REFRESHER, "Refresher"),
        (TYPE_SPECIFIC, "Specific"),
        (TYPE_EMERGENCY, "Emergency"),
        (TYPE_REGULATORY, "Regulatory"),
    ]

    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    training_name = models.CharField(max_length=255)
    training_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField(blank=True)
    trainer = models.CharField(max_length=150)
    scheduled_date = models.DateTimeField()
    duration_hours = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    location = models.CharField(max_length=150, blank=True)
    max_attendees = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    materials_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trainings_created",
    )

    class Meta:
        ordering = ["-scheduled_date"]


class TrainingAttendee(BaseModel):
    training = models.ForeignKey(
        SafetyTraining, on_delete=models.CASCADE, related_name="attendees"
    )
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.CASCADE, related_name="training_attendance"
    )
    attended = models.BooleanField(default=False)
    certificate_issued = models.BooleanField(default=False)
    certificate_expiry = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("training", "employee")]


# Security sub-department models (imported for migrations)
from apps.safety.security_models import (  # noqa: E402, F401
    AccessLog,
    AccessZone,
    InterLocationMovement,
    SecurityIncidentRecord,
    SecurityLocation,
    SecurityPersonnel,
    SecurityShift,
    SecurityShiftOfficer,
    VehicleLog,
    Visitor,
)
