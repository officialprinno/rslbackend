"""django-filter FilterSets for HR endpoints."""

import django_filters

from apps.hr.models import (
    Appraisal,
    Attendance,
    DisciplinaryRecord,
    Employee,
    LeaveRequest,
    Payroll,
)


class EmployeeFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="department_id")
    employment_type = django_filters.CharFilter()
    status = django_filters.CharFilter()

    class Meta:
        model = Employee
        fields = ["department", "employment_type", "status", "is_active"]


class AttendanceFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="employee__department_id")
    employee = django_filters.NumberFilter(field_name="employee_id")
    date = django_filters.DateFilter()
    month = django_filters.NumberFilter(field_name="date", lookup_expr="month")
    year = django_filters.NumberFilter(field_name="date", lookup_expr="year")

    class Meta:
        model = Attendance
        fields = ["status", "employee", "date", "month", "year"]


class LeaveRequestFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="employee__department_id")
    leave_type = django_filters.NumberFilter(field_name="leave_type_id")
    date_from = django_filters.DateFilter(field_name="start_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="end_date", lookup_expr="lte")

    class Meta:
        model = LeaveRequest
        fields = ["status", "leave_type", "employee"]


class PayrollFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="department_id")
    period_year = django_filters.NumberFilter()
    period_month = django_filters.NumberFilter()

    class Meta:
        model = Payroll
        fields = ["status", "department", "period_year", "period_month"]


class AppraisalFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="employee__department_id")
    employee = django_filters.NumberFilter(field_name="employee_id")

    class Meta:
        model = Appraisal
        fields = ["status", "employee", "department"]


class DisciplinaryFilter(django_filters.FilterSet):
    employee = django_filters.NumberFilter(field_name="employee_id")

    class Meta:
        model = DisciplinaryRecord
        fields = ["record_type", "employee"]
