"""
HR models for Rock Solutions FMS — Tanzania payroll & HR management.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class LeaveType(BaseModel):
  """Configurable leave types."""

  name = models.CharField(max_length=100, unique=True)
  code = models.CharField(max_length=30, unique=True)
  days_entitled = models.PositiveIntegerField(default=0)
  is_paid = models.BooleanField(default=True)
  carry_forward = models.BooleanField(default=False)
  description = models.TextField(blank=True)

  class Meta:
    ordering = ["name"]

  def __str__(self):
    return self.name


class AllowanceConfig(BaseModel):
  """System-wide allowance configuration."""

  name = models.CharField(max_length=100)
  amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  is_taxable = models.BooleanField(default=True)
  department = models.ForeignKey(
    "users.Department",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="allowance_configs",
    help_text="Null = applies to all departments",
  )
  effective_date = models.DateField(default=timezone.now)
  end_date = models.DateField(null=True, blank=True)

  class Meta:
    ordering = ["name"]

  def __str__(self):
    return self.name


class Employee(BaseModel):
  """Employee master record."""

  GENDER_MALE = "MALE"
  GENDER_FEMALE = "FEMALE"
  GENDER_CHOICES = [(GENDER_MALE, "Male"), (GENDER_FEMALE, "Female")]

  EMP_PERMANENT = "PERMANENT"
  EMP_CONTRACT = "CONTRACT"
  EMP_CASUAL = "CASUAL"
  EMPLOYMENT_TYPE_CHOICES = [
    (EMP_PERMANENT, "Permanent"),
    (EMP_CONTRACT, "Contract"),
    (EMP_CASUAL, "Casual"),
  ]

  STATUS_DRAFT = "DRAFT"
  STATUS_ACTIVE = "ACTIVE"
  STATUS_INACTIVE = "INACTIVE"
  STATUS_CHOICES = [
    (STATUS_DRAFT, "Draft"),
    (STATUS_ACTIVE, "Active"),
    (STATUS_INACTIVE, "Inactive"),
  ]

  FREQ_MONTHLY = "MONTHLY"
  FREQ_WEEKLY = "WEEKLY"
  PAYMENT_FREQ_CHOICES = [
    (FREQ_MONTHLY, "Monthly"),
    (FREQ_WEEKLY, "Weekly"),
  ]

  employee_number = models.CharField(max_length=30, unique=True, editable=False)
  user = models.OneToOneField(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="employee_profile",
  )
  first_name = models.CharField(max_length=100)
  last_name = models.CharField(max_length=100)
  gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default=GENDER_MALE)
  date_of_birth = models.DateField(null=True, blank=True)
  national_id = models.CharField(max_length=50, blank=True)
  tin_number = models.CharField(max_length=50, blank=True)
  nssf_number = models.CharField(max_length=50, blank=True)
  nhif_number = models.CharField(max_length=50, blank=True)
  paye_applicable = models.BooleanField(default=True)
  phone = models.CharField(max_length=30, blank=True)
  personal_email = models.EmailField(blank=True)
  work_email = models.EmailField(blank=True)
  address = models.TextField(blank=True)
  city = models.CharField(max_length=100, blank=True)
  profile_photo = models.CharField(max_length=500, blank=True)
  department = models.ForeignKey(
    "users.Department",
    on_delete=models.PROTECT,
    related_name="employees",
  )
  job_title = models.CharField(max_length=150)
  employment_type = models.CharField(
    max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default=EMP_PERMANENT
  )
  contract_start = models.DateField(null=True, blank=True)
  contract_end = models.DateField(null=True, blank=True)
  probation_end = models.DateField(null=True, blank=True)
  reports_to = models.ForeignKey(
    "self",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="direct_reports",
  )
  basic_salary = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  currency = models.ForeignKey(
    "core.Currency",
    on_delete=models.PROTECT,
    related_name="employees",
  )
  payment_frequency = models.CharField(
    max_length=20, choices=PAYMENT_FREQ_CHOICES, default=FREQ_MONTHLY
  )
  bank_name = models.CharField(max_length=100, blank=True)
  bank_account = models.CharField(max_length=50, blank=True)
  bank_account_name = models.CharField(max_length=255, blank=True)
  bank_branch = models.CharField(max_length=100, blank=True)
  emergency_contact_name = models.CharField(max_length=150, blank=True)
  emergency_contact_relationship = models.CharField(max_length=50, blank=True)
  emergency_contact_phone = models.CharField(max_length=30, blank=True)
  emergency_contact_address = models.TextField(blank=True)
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
  create_user_account = models.BooleanField(default=False)
  resignation_date = models.DateField(null=True, blank=True)

  class Meta:
    ordering = ["employee_number"]

  def __str__(self):
    return f"{self.employee_number} — {self.full_name}"

  @property
  def full_name(self):
    return f"{self.first_name} {self.last_name}".strip()


class EmployeeAllowance(BaseModel):
  """Employee-specific allowance."""

  employee = models.ForeignKey(
    Employee, on_delete=models.CASCADE, related_name="allowances"
  )
  name = models.CharField(max_length=100)
  amount = models.DecimalField(max_digits=18, decimal_places=2)
  is_taxable = models.BooleanField(default=True)
  effective_date = models.DateField(default=timezone.now)

  class Meta:
    ordering = ["name"]


class EmployeeDocument(BaseModel):
  """Employee document storage reference."""

  DOC_CONTRACT = "CONTRACT"
  DOC_NIN = "NIN"
  DOC_CERTIFICATE = "CERTIFICATE"
  DOC_OTHER = "OTHER"
  DOC_TYPE_CHOICES = [
    (DOC_CONTRACT, "Contract"),
    (DOC_NIN, "National ID"),
    (DOC_CERTIFICATE, "Certificate"),
    (DOC_OTHER, "Other"),
  ]

  employee = models.ForeignKey(
    Employee, on_delete=models.CASCADE, related_name="documents"
  )
  doc_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES)
  name = models.CharField(max_length=255)
  file_url = models.CharField(max_length=500, blank=True)
  expiry_date = models.DateField(null=True, blank=True)
  is_expired = models.BooleanField(default=False)


class Attendance(BaseModel):
  """Daily attendance record."""

  STATUS_PRESENT = "PRESENT"
  STATUS_ABSENT = "ABSENT"
  STATUS_LATE = "LATE"
  STATUS_HALF_DAY = "HALF_DAY"
  STATUS_LEAVE = "LEAVE"
  STATUS_CHOICES = [
    (STATUS_PRESENT, "Present"),
    (STATUS_ABSENT, "Absent"),
    (STATUS_LATE, "Late"),
    (STATUS_HALF_DAY, "Half Day"),
    (STATUS_LEAVE, "Leave"),
  ]

  employee = models.ForeignKey(
    Employee, on_delete=models.CASCADE, related_name="attendance_records"
  )
  date = models.DateField()
  time_in = models.TimeField(null=True, blank=True)
  time_out = models.TimeField(null=True, blank=True)
  hours_worked = models.DecimalField(
    max_digits=5, decimal_places=2, default=Decimal("0")
  )
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PRESENT)
  notes = models.TextField(blank=True)
  marked_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="attendance_marked",
  )

  class Meta:
    ordering = ["-date"]
    unique_together = [("employee", "date")]


class LeaveRequest(BaseModel):
  """Employee leave application."""

  STATUS_PENDING = "PENDING"
  STATUS_APPROVED = "APPROVED"
  STATUS_REJECTED = "REJECTED"
  STATUS_CHOICES = [
    (STATUS_PENDING, "Pending"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_REJECTED, "Rejected"),
  ]

  employee = models.ForeignKey(
    Employee, on_delete=models.CASCADE, related_name="leave_requests"
  )
  leave_type = models.ForeignKey(
    LeaveType, on_delete=models.PROTECT, related_name="requests"
  )
  start_date = models.DateField()
  end_date = models.DateField()
  days_requested = models.PositiveIntegerField(default=1)
  reason = models.TextField(blank=True)
  medical_certificate = models.CharField(max_length=500, blank=True)
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
  approved_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="leave_approved",
  )
  approved_at = models.DateTimeField(null=True, blank=True)
  rejection_reason = models.TextField(blank=True)

  class Meta:
    ordering = ["-created_at"]


class Payroll(BaseModel):
  """Monthly payroll batch."""

  STATUS_DRAFT = "DRAFT"
  STATUS_REVIEWED = "REVIEWED"
  STATUS_APPROVED = "APPROVED"
  STATUS_PAID = "PAID"
  STATUS_CHOICES = [
    (STATUS_DRAFT, "Draft"),
    (STATUS_REVIEWED, "Reviewed"),
    (STATUS_APPROVED, "Approved"),
    (STATUS_PAID, "Paid"),
  ]

  payroll_number = models.CharField(max_length=30, unique=True, editable=False)
  period_month = models.PositiveSmallIntegerField(
    validators=[MinValueValidator(1), MaxValueValidator(12)]
  )
  period_year = models.PositiveIntegerField()
  department = models.ForeignKey(
    "users.Department",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="payrolls",
  )
  total_employees = models.PositiveIntegerField(default=0)
  total_gross = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  total_nssf_employee = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  total_nssf_employer = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  total_paye = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  total_nhif = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  total_deductions = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  total_net = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
  processed_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="payrolls_processed",
  )
  approved_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="payrolls_approved",
  )
  approved_at = models.DateTimeField(null=True, blank=True)
  paid_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    ordering = ["-period_year", "-period_month"]
    unique_together = [("period_month", "period_year", "department")]

  def __str__(self):
    return self.payroll_number


class PayrollItem(BaseModel):
  """Per-employee payroll line."""

  payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name="items")
  employee = models.ForeignKey(
    Employee, on_delete=models.PROTECT, related_name="payroll_items"
  )
  basic_salary = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  allowances_json = models.JSONField(default=list, blank=True)
  total_allowances = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  gross_salary = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  nssf_employee = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  nssf_employer = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  paye = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  nhif = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
  other_deductions = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  total_deductions = models.DecimalField(
    max_digits=18, decimal_places=2, default=Decimal("0")
  )
  net_salary = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

  class Meta:
    ordering = ["employee__employee_number"]
    unique_together = [("payroll", "employee")]


class Appraisal(BaseModel):
  """Performance appraisal."""

  STATUS_SCHEDULED = "SCHEDULED"
  STATUS_COMPLETED = "COMPLETED"
  STATUS_CHOICES = [
    (STATUS_SCHEDULED, "Scheduled"),
    (STATUS_COMPLETED, "Completed"),
  ]

  PERIOD_QUARTER = "QUARTER"
  PERIOD_ANNUAL = "ANNUAL"
  PERIOD_CHOICES = [(PERIOD_QUARTER, "Quarter"), (PERIOD_ANNUAL, "Annual")]

  employee = models.ForeignKey(
    Employee, on_delete=models.CASCADE, related_name="appraisals"
  )
  period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default=PERIOD_ANNUAL)
  period_label = models.CharField(max_length=100, blank=True)
  score = models.PositiveSmallIntegerField(
    null=True, blank=True, validators=[MaxValueValidator(100)]
  )
  rating = models.CharField(max_length=30, blank=True)
  reviewer = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="appraisals_reviewed",
  )
  strengths = models.TextField(blank=True)
  improvements = models.TextField(blank=True)
  goals = models.TextField(blank=True)
  comments = models.TextField(blank=True)
  employee_acknowledged = models.BooleanField(default=False)
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
  scheduled_date = models.DateField()
  completed_at = models.DateTimeField(null=True, blank=True)

  class Meta:
    ordering = ["-scheduled_date"]


class DisciplinaryRecord(BaseModel):
  """Confidential disciplinary record."""

  TYPE_VERBAL = "VERBAL_WARNING"
  TYPE_WRITTEN = "WRITTEN_WARNING"
  TYPE_FINAL = "FINAL_WARNING"
  TYPE_SUSPENSION = "SUSPENSION"
  TYPE_TERMINATION = "TERMINATION"
  TYPE_CHOICES = [
    (TYPE_VERBAL, "Verbal Warning"),
    (TYPE_WRITTEN, "Written Warning"),
    (TYPE_FINAL, "Final Warning"),
    (TYPE_SUSPENSION, "Suspension"),
    (TYPE_TERMINATION, "Termination"),
  ]

  employee = models.ForeignKey(
    Employee, on_delete=models.CASCADE, related_name="disciplinary_records"
  )
  incident_date = models.DateField()
  record_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
  description = models.TextField()
  action_taken = models.TextField(blank=True)
  issued_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="disciplinary_issued",
  )
  witness = models.CharField(max_length=150, blank=True)
  employee_acknowledged = models.BooleanField(default=False)
  is_confidential = models.BooleanField(default=True)

  class Meta:
    ordering = ["-incident_date"]


class PublicHoliday(BaseModel):
  """Public holiday calendar."""

  name = models.CharField(max_length=150)
  date = models.DateField()
  is_variable = models.BooleanField(default=False)
  year = models.PositiveIntegerField()

  class Meta:
    ordering = ["date"]
    unique_together = [("name", "year")]


class WorkingHoursConfig(BaseModel):
  """Singleton working hours configuration."""

  hours_per_day = models.DecimalField(
    max_digits=4, decimal_places=2, default=Decimal("8")
  )
  working_days = models.CharField(
    max_length=50, default="MON,TUE,WED,THU,FRI"
  )

  class Meta:
    verbose_name = "Working Hours Configuration"


class CompanyProfile(BaseModel):
  """HR company profile settings."""

  company_name = models.CharField(max_length=255, default="Rock Solutions Limited")
  tin = models.CharField(max_length=50, default="127-950-695")
  vat_number = models.CharField(max_length=50, default="40022138R")
  address = models.TextField(default="Plot 252 Block L, Misungwi, Mwanza")
  phone = models.CharField(max_length=30, blank=True)
  email = models.EmailField(blank=True)
  website = models.URLField(blank=True)
  logo_url = models.CharField(max_length=500, blank=True)

  class Meta:
    verbose_name = "Company Profile"
