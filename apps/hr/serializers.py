"""Serializers for the HR module."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.hr.models import (
    AllowanceConfig,
    Appraisal,
    Attendance,
    CompanyProfile,
    DisciplinaryRecord,
    Employee,
    EmployeeAllowance,
    EmployeeDocument,
    LeaveRequest,
    LeaveType,
    Payroll,
    PayrollItem,
    PublicHoliday,
    WorkingHoursConfig,
)
from apps.hr.payroll_utils import appraisal_rating, count_working_days
from apps.hr.services import HRService


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            "id", "name", "code", "days_entitled", "is_paid",
            "carry_forward", "description", "is_active",
        ]


class AllowanceConfigSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(
        source="department.name", read_only=True, allow_null=True
    )

    class Meta:
        model = AllowanceConfig
        fields = [
            "id", "name", "amount", "is_taxable", "department",
            "department_name", "effective_date", "end_date", "is_active",
        ]


class EmployeeAllowanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeAllowance
        fields = ["id", "name", "amount", "is_taxable", "effective_date", "is_active"]


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeDocument
        fields = [
            "id", "doc_type", "name", "file_url", "expiry_date", "is_expired", "is_active",
        ]


class EmployeeListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    reports_to_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id", "employee_number", "full_name", "first_name", "last_name",
            "department_id", "department_name", "job_title", "employment_type",
            "contract_end", "basic_salary", "currency_code", "status", "is_active",
            "profile_photo", "phone", "national_id", "reports_to_name",
        ]

    def get_reports_to_name(self, obj):
        return obj.reports_to.full_name if obj.reports_to else None


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    reports_to_name = serializers.SerializerMethodField()
    allowances = EmployeeAllowanceSerializer(many=True, required=False)
    documents = EmployeeDocumentSerializer(many=True, read_only=True)
    leave_balances = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source="user.id", read_only=True, allow_null=True)

    class Meta:
        model = Employee
        fields = [
            "id", "employee_number", "user_id", "first_name", "last_name", "full_name",
            "gender", "date_of_birth", "national_id", "tin_number", "nssf_number",
            "nhif_number", "paye_applicable", "phone", "personal_email", "work_email",
            "address", "city", "profile_photo", "department", "department_name",
            "job_title", "employment_type", "contract_start", "contract_end",
            "probation_end", "reports_to", "reports_to_name", "basic_salary",
            "currency", "currency_code", "payment_frequency", "bank_name",
            "bank_account", "bank_account_name", "bank_branch",
            "emergency_contact_name", "emergency_contact_relationship",
            "emergency_contact_phone", "emergency_contact_address",
            "status", "is_active", "create_user_account", "allowances",
            "documents", "leave_balances", "created_at", "updated_at",
        ]
        read_only_fields = ["employee_number", "created_at", "updated_at"]

    def get_reports_to_name(self, obj):
        return obj.reports_to.full_name if obj.reports_to else None

    def get_leave_balances(self, obj):
        return HRService.leave_balance(obj)

    @transaction.atomic
    def create(self, validated_data):
        allowances_data = validated_data.pop("allowances", [])
        status = validated_data.get("status", Employee.STATUS_DRAFT)
        if status == Employee.STATUS_ACTIVE:
            validated_data["is_active"] = True
        elif status == Employee.STATUS_INACTIVE:
            validated_data["is_active"] = False
        HRService.prepare_employee(validated_data)
        employee = Employee.objects.create(**validated_data)
        for a in allowances_data:
            EmployeeAllowance.objects.create(employee=employee, **a)
        return employee

    @transaction.atomic
    def update(self, instance, validated_data):
        allowances_data = validated_data.pop("allowances", None)
        status = validated_data.get("status")
        if status == Employee.STATUS_ACTIVE:
            validated_data["is_active"] = True
            validated_data["resignation_date"] = None
        elif status == Employee.STATUS_INACTIVE:
            validated_data["is_active"] = False
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if allowances_data is not None:
            instance.allowances.all().delete()
            for a in allowances_data:
                EmployeeAllowance.objects.create(employee=instance, **a)
        return instance


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_name", "department_name", "date",
            "time_in", "time_out", "hours_worked", "status", "notes",
        ]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "employee", "employee_name", "department_name",
            "leave_type", "leave_type_name", "start_date", "end_date",
            "days_requested", "reason", "medical_certificate", "status",
            "approved_by_name", "approved_at", "rejection_reason", "created_at",
        ]
        read_only_fields = ["status", "approved_at", "created_at"]

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.email
        return None

    def create(self, validated_data):
        start = validated_data["start_date"]
        end = validated_data["end_date"]
        validated_data["days_requested"] = count_working_days(start, end)
        return super().create(validated_data)


class PayrollItemSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)
    allowances = serializers.JSONField(source="allowances_json")

    class Meta:
        model = PayrollItem
        fields = [
            "id", "employee", "employee_name", "employee_number", "department_name",
            "basic_salary", "allowances", "total_allowances", "gross_salary",
            "nssf_employee", "nssf_employer", "paye", "nhif", "other_deductions",
            "total_deductions", "net_salary",
        ]


class PayrollSerializer(serializers.ModelSerializer):
    items = PayrollItemSerializer(many=True, read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True)
    period_display = serializers.SerializerMethodField()
    processed_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payroll
        fields = [
            "id", "payroll_number", "period_month", "period_year", "period_display",
            "department", "department_name", "total_employees", "total_gross",
            "total_nssf_employee", "total_nssf_employer", "total_paye", "total_nhif",
            "total_deductions", "total_net", "status", "items",
            "processed_by_name", "approved_by_name", "approved_at", "paid_at", "created_at",
        ]
        read_only_fields = [
            "payroll_number", "total_employees", "total_gross", "total_nssf_employee",
            "total_nssf_employer", "total_paye", "total_nhif", "total_deductions",
            "total_net", "status", "created_at",
        ]

    def get_period_display(self, obj):
        months = ["", "January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        return f"{months[obj.period_month]} {obj.period_year}"

    def get_processed_by_name(self, obj):
        if obj.processed_by:
            return obj.processed_by.get_full_name() or obj.processed_by.email
        return None

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.email
        return None


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)
    period_display = serializers.SerializerMethodField()
    job_title = serializers.CharField(source="employee.job_title", read_only=True)
    tin_number = serializers.CharField(source="employee.tin_number", read_only=True)
    nssf_number = serializers.CharField(source="employee.nssf_number", read_only=True)
    bank_name = serializers.CharField(source="employee.bank_name", read_only=True)
    bank_account = serializers.CharField(source="employee.bank_account", read_only=True)
    allowances = serializers.JSONField(source="allowances_json")

    class Meta:
        model = PayrollItem
        fields = [
            "id", "employee", "employee_name", "employee_number", "department_name",
            "job_title", "tin_number", "nssf_number", "bank_name", "bank_account",
            "period_display", "basic_salary", "allowances", "total_allowances",
            "gross_salary", "nssf_employee", "paye", "nhif", "other_deductions",
            "total_deductions", "net_salary", "nssf_employer",
        ]

    def get_period_display(self, obj):
        p = obj.payroll
        months = ["", "January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        return f"{months[p.period_month]} {p.period_year}"


class AppraisalSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(source="employee.department.name", read_only=True)
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = Appraisal
        fields = [
            "id", "employee", "employee_name", "department_name", "period",
            "period_label", "score", "rating", "reviewer", "reviewer_name",
            "strengths", "improvements", "goals", "comments",
            "employee_acknowledged", "status", "scheduled_date", "completed_at",
        ]

    def get_reviewer_name(self, obj):
        if obj.reviewer:
            return obj.reviewer.get_full_name() or obj.reviewer.email
        return None


class DisciplinaryRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    issued_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DisciplinaryRecord
        fields = [
            "id", "employee", "employee_name", "incident_date", "record_type",
            "description", "action_taken", "issued_by", "issued_by_name",
            "witness", "employee_acknowledged", "is_confidential", "created_at",
        ]
        read_only_fields = ["issued_by", "created_at"]

    def get_issued_by_name(self, obj):
        if obj.issued_by:
            return obj.issued_by.get_full_name() or obj.issued_by.email
        return None


class PublicHolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicHoliday
        fields = ["id", "name", "date", "is_variable", "year", "is_active"]


class WorkingHoursConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkingHoursConfig
        fields = ["id", "hours_per_day", "working_days", "is_active"]


class CompanyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyProfile
        fields = [
            "id", "company_name", "tin", "vat_number", "address",
            "phone", "email", "website", "logo_url",
        ]
