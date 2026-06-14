"""HR module utilities."""

from django.utils import timezone


def generate_employee_number():
    from apps.hr.models import Employee

    prefix = "RSL-EMP-"
    last = (
        Employee.objects.filter(employee_number__startswith=prefix)
        .order_by("-employee_number")
        .values_list("employee_number", flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.replace(prefix, "")) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"


def generate_payroll_number(year=None):
    from apps.hr.models import Payroll

    year = year or timezone.now().year
    prefix = f"PAY-{year}-"
    last = (
        Payroll.objects.filter(payroll_number__startswith=prefix)
        .order_by("-payroll_number")
        .values_list("payroll_number", flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"


def work_email_from_name(first_name, last_name):
    first = (first_name or "").strip().lower().replace(" ", "")
    return f"{first}@rocksolutions.co.tz" if first else ""
