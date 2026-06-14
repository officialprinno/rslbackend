"""Security sub-department models — Rock Solutions Limited."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class SecurityLocation(BaseModel):
    """Main Office and Stein factory sites."""

    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default="#1B3A6B")
    icon = models.CharField(max_length=10, default="🏢")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Visitor(BaseModel):
    ID_NATIONAL = "NATIONAL_ID"
    ID_PASSPORT = "PASSPORT"
    ID_LICENCE = "DRIVING_LICENCE"
    ID_CHOICES = [
        (ID_NATIONAL, "National ID"),
        (ID_PASSPORT, "Passport"),
        (ID_LICENCE, "Driving Licence"),
    ]

    PURPOSE_MEETING = "MEETING"
    PURPOSE_DELIVERY = "DELIVERY"
    PURPOSE_CONTRACTOR = "CONTRACTOR"
    PURPOSE_INSPECTION = "INSPECTION"
    PURPOSE_OTHER = "OTHER"
    PURPOSE_CHOICES = [
        (PURPOSE_MEETING, "Meeting"),
        (PURPOSE_DELIVERY, "Delivery"),
        (PURPOSE_CONTRACTOR, "Contractor"),
        (PURPOSE_INSPECTION, "Inspection"),
        (PURPOSE_OTHER, "Other"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_SIGNED_IN = "SIGNED_IN"
    STATUS_SIGNED_OUT = "SIGNED_OUT"
    STATUS_OVERSTAYING = "OVERSTAYING"
    STATUS_DENIED = "DENIED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SIGNED_IN, "Signed In"),
        (STATUS_SIGNED_OUT, "Signed Out"),
        (STATUS_OVERSTAYING, "Overstaying"),
        (STATUS_DENIED, "Denied"),
    ]

    visitor_number = models.CharField(max_length=30, unique=True, editable=False)
    full_name = models.CharField(max_length=200)
    id_type = models.CharField(max_length=20, choices=ID_CHOICES, default=ID_NATIONAL)
    id_number = models.CharField(max_length=50)
    phone = models.CharField(max_length=30)
    company = models.CharField(max_length=200, blank=True)
    photo_url = models.CharField(max_length=500, blank=True)
    email = models.EmailField(blank=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    host_employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="hosted_visitors",
    )
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.PROTECT,
        related_name="visitors",
    )
    expected_time_in = models.DateTimeField()
    expected_time_out = models.DateTimeField()
    actual_time_in = models.DateTimeField(null=True, blank=True)
    actual_time_out = models.DateTimeField(null=True, blank=True)
    badge_number = models.CharField(max_length=30, blank=True)
    vehicle_registration = models.CharField(max_length=30, blank=True)
    items_brought = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    denial_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    pre_approved = models.BooleanField(default=False)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="visitors_registered",
    )

    class Meta:
        ordering = ["-created_at"]


class VehicleLog(BaseModel):
    TYPE_COMPANY = "COMPANY"
    TYPE_EMPLOYEE = "EMPLOYEE"
    TYPE_VISITOR = "VISITOR"
    TYPE_SUPPLIER = "SUPPLIER"
    TYPE_CONTRACTOR = "CONTRACTOR"
    TYPE_UNKNOWN = "UNKNOWN"
    TYPE_CHOICES = [
        (TYPE_COMPANY, "Company"),
        (TYPE_EMPLOYEE, "Employee"),
        (TYPE_VISITOR, "Visitor"),
        (TYPE_SUPPLIER, "Supplier"),
        (TYPE_CONTRACTOR, "Contractor"),
        (TYPE_UNKNOWN, "Unknown"),
    ]

    STATUS_ON = "ON_PREMISES"
    STATUS_EXITED = "EXITED"
    STATUS_FLAGGED = "FLAGGED"
    STATUS_CHOICES = [
        (STATUS_ON, "On Premises"),
        (STATUS_EXITED, "Exited"),
        (STATUS_FLAGGED, "Flagged"),
    ]

    log_number = models.CharField(max_length=30, unique=True, editable=False)
    registration_number = models.CharField(max_length=30)
    vehicle_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    make = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=50, blank=True)
    driver_name = models.CharField(max_length=200)
    driver_id_number = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=200, blank=True)
    purpose = models.CharField(max_length=100, blank=True)
    occupants_count = models.PositiveIntegerField(default=1)
    cargo_description = models.TextField(blank=True)
    location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.PROTECT,
        related_name="vehicle_logs",
    )
    time_in = models.DateTimeField()
    time_out = models.DateTimeField(null=True, blank=True)
    expected_time_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ON)
    flag_reason = models.TextField(blank=True)
    security_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="vehicle_logs_logged",
    )

    class Meta:
        ordering = ["-time_in"]


class SecurityPersonnel(BaseModel):
    RANK_CHIEF = "CHIEF"
    RANK_SUPERVISOR = "SUPERVISOR"
    RANK_OFFICER = "OFFICER"
    RANK_GUARD = "GUARD"
    RANK_CHOICES = [
        (RANK_CHIEF, "Chief Security Officer"),
        (RANK_SUPERVISOR, "Security Supervisor"),
        (RANK_OFFICER, "Security Officer"),
        (RANK_GUARD, "Security Guard"),
    ]

    SCOPE_MAIN = "MAIN_OFFICE"
    SCOPE_STEIN = "STEIN"
    SCOPE_BOTH = "BOTH"
    SCOPE_CHOICES = [
        (SCOPE_MAIN, "Main Office"),
        (SCOPE_STEIN, "Stein"),
        (SCOPE_BOTH, "Both Locations"),
    ]

    employee = models.OneToOneField(
        "hr.Employee",
        on_delete=models.CASCADE,
        related_name="security_profile",
    )
    rank = models.CharField(max_length=20, choices=RANK_CHOICES, default=RANK_GUARD)
    primary_location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_personnel",
    )
    assignment_scope = models.CharField(
        max_length=20, choices=SCOPE_CHOICES, default=SCOPE_MAIN
    )
    post_station = models.CharField(max_length=100, blank=True)
    certification_number = models.CharField(max_length=100, blank=True)
    certification_expiry = models.DateField(null=True, blank=True)
    is_on_duty = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Security personnel"


class SecurityShift(BaseModel):
    SHIFT_MORNING = "MORNING"
    SHIFT_AFTERNOON = "AFTERNOON"
    SHIFT_NIGHT = "NIGHT"
    SHIFT_CHOICES = [
        (SHIFT_MORNING, "Morning"),
        (SHIFT_AFTERNOON, "Afternoon"),
        (SHIFT_NIGHT, "Night"),
    ]

    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
    ]

    date = models.DateField()
    shift_type = models.CharField(max_length=20, choices=SHIFT_CHOICES)
    location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.PROTECT,
        related_name="shifts",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    special_instructions = models.TextField(blank=True)
    incidents_count = models.PositiveIntegerField(default=0)
    handover_submitted = models.BooleanField(default=False)
    handover_notes = models.TextField(blank=True)
    outgoing_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts_outgoing",
    )
    incoming_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts_incoming",
    )

    class Meta:
        ordering = ["-date", "shift_type"]
        unique_together = [("date", "shift_type", "location")]


class SecurityShiftOfficer(BaseModel):
    shift = models.ForeignKey(
        SecurityShift, on_delete=models.CASCADE, related_name="officers"
    )
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="security_shift_assignments",
    )
    post_station = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = [("shift", "officer")]


class AccessZone(BaseModel):
    LEVEL_PUBLIC = "PUBLIC"
    LEVEL_STAFF = "STAFF_ONLY"
    LEVEL_AUTHORIZED = "AUTHORIZED_ONLY"
    LEVEL_RESTRICTED = "RESTRICTED"
    LEVEL_CHOICES = [
        (LEVEL_PUBLIC, "Public"),
        (LEVEL_STAFF, "Staff Only"),
        (LEVEL_AUTHORIZED, "Authorized Only"),
        (LEVEL_RESTRICTED, "Restricted"),
    ]

    location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.CASCADE,
        related_name="access_zones",
    )
    name = models.CharField(max_length=100)
    access_level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default=LEVEL_PUBLIC)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["location", "name"]
        unique_together = [("location", "name")]


class AccessLog(BaseModel):
    PERSON_EMPLOYEE = "EMPLOYEE"
    PERSON_VISITOR = "VISITOR"
    PERSON_VEHICLE = "VEHICLE"
    PERSON_CHOICES = [
        (PERSON_EMPLOYEE, "Employee"),
        (PERSON_VISITOR, "Visitor"),
        (PERSON_VEHICLE, "Vehicle"),
    ]

    ACTION_GRANTED = "GRANTED"
    ACTION_DENIED = "DENIED"
    ACTION_FORCED = "FORCED"
    ACTION_CHOICES = [
        (ACTION_GRANTED, "Granted"),
        (ACTION_DENIED, "Denied"),
        (ACTION_FORCED, "Forced"),
    ]

    METHOD_CARD = "CARD"
    METHOD_MANUAL = "MANUAL"
    METHOD_BIOMETRIC = "BIOMETRIC"
    METHOD_CHOICES = [
        (METHOD_CARD, "Card"),
        (METHOD_MANUAL, "Manual"),
        (METHOD_BIOMETRIC, "Biometric"),
    ]

    zone = models.ForeignKey(
        AccessZone, on_delete=models.SET_NULL, null=True, related_name="access_logs"
    )
    location = models.ForeignKey(
        SecurityLocation, on_delete=models.PROTECT, related_name="access_logs"
    )
    person_name = models.CharField(max_length=200)
    person_type = models.CharField(max_length=20, choices=PERSON_CHOICES)
    employee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_log_entries",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_MANUAL)
    security_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="access_logs_recorded",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class SecurityIncidentRecord(BaseModel):
    """Security-specific incidents (distinct from HSE SafetyIncident)."""

    TYPE_THEFT = "THEFT"
    TYPE_TRESPASSING = "TRESPASSING"
    TYPE_VANDALISM = "VANDALISM"
    TYPE_ASSAULT = "ASSAULT"
    TYPE_UNAUTHORIZED = "UNAUTHORIZED_ACCESS"
    TYPE_SUSPICIOUS = "SUSPICIOUS_ACTIVITY"
    TYPE_DAMAGE = "PROPERTY_DAMAGE"
    TYPE_FRAUD = "FRAUD"
    TYPE_ROAD = "ROAD_INCIDENT"
    TYPE_OTHER = "OTHER"
    TYPE_CHOICES = [
        (TYPE_THEFT, "Theft"),
        (TYPE_TRESPASSING, "Trespassing"),
        (TYPE_VANDALISM, "Vandalism"),
        (TYPE_ASSAULT, "Assault"),
        (TYPE_UNAUTHORIZED, "Unauthorized Access"),
        (TYPE_SUSPICIOUS, "Suspicious Activity"),
        (TYPE_DAMAGE, "Property Damage"),
        (TYPE_FRAUD, "Fraud"),
        (TYPE_ROAD, "Road Incident"),
        (TYPE_OTHER, "Other"),
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

    STATUS_OPEN = "OPEN"
    STATUS_INVESTIGATING = "INVESTIGATING"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_INVESTIGATING, "Investigating"),
        (STATUS_CLOSED, "Closed"),
    ]

    incident_number = models.CharField(max_length=30, unique=True, editable=False)
    incident_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    date_occurred = models.DateTimeField()
    location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.PROTECT,
        related_name="security_incidents",
    )
    specific_area = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    persons_involved = models.TextField(blank=True)
    immediate_actions = models.TextField(blank=True)
    police_report_number = models.CharField(max_length=100, blank=True)
    evidence_photos = models.JSONField(default=list, blank=True)
    investigation_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="security_incidents_reported",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="security_incidents_closed",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date_occurred"]


class InterLocationMovement(BaseModel):
    TYPE_EMPLOYEE = "EMPLOYEE"
    TYPE_VEHICLE = "VEHICLE"
    TYPE_CHOICES = [
        (TYPE_EMPLOYEE, "Employee"),
        (TYPE_VEHICLE, "Vehicle"),
    ]

    STATUS_TRANSIT = "IN_TRANSIT"
    STATUS_ARRIVED = "ARRIVED"
    STATUS_OVERDUE = "OVERDUE"
    STATUS_CHOICES = [
        (STATUS_TRANSIT, "In Transit"),
        (STATUS_ARRIVED, "Arrived"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    movement_number = models.CharField(max_length=30, unique=True, editable=False)
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inter_location_movements",
    )
    vehicle_log = models.ForeignKey(
        VehicleLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )
    from_location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.PROTECT,
        related_name="movements_from",
    )
    to_location = models.ForeignKey(
        SecurityLocation,
        on_delete=models.PROTECT,
        related_name="movements_to",
    )
    departure_time = models.DateTimeField()
    expected_arrival = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    travel_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRANSIT)
    purpose = models.CharField(max_length=255)
    passengers = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="movements_logged",
    )
    arrived_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements_confirmed",
    )

    class Meta:
        ordering = ["-departure_time"]
