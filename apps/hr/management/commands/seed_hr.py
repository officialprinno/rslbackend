"""
Seed HR data: leave types, allowances, employees, attendance, holidays.

Prerequisites: seed_fms, seed_finance (for currency)
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Currency
from apps.hr.models import (
    AllowanceConfig,
    Appraisal,
    Attendance,
    CompanyProfile,
    Employee,
    EmployeeAllowance,
    LeaveRequest,
    LeaveType,
    PublicHoliday,
    WorkingHoursConfig,
)
from apps.users.models import Department, User

LEAVE_TYPES = [
    ("ANNUAL", "Annual Leave", 28, True, True),
    ("SICK", "Sick Leave", 14, True, False),
    ("MATERNITY", "Maternity Leave", 84, True, False),
    ("PATERNITY", "Paternity Leave", 3, True, False),
    ("COMPASSIONATE", "Compassionate Leave", 3, True, False),
]

TZ_HOLIDAYS_2026 = [
    ("New Year's Day", date(2026, 1, 1)),
    ("Zanzibar Revolution Day", date(2026, 1, 12)),
    ("Union Day", date(2026, 4, 26)),
    ("Workers' Day", date(2026, 5, 1)),
    ("Saba Saba", date(2026, 7, 7)),
    ("Nane Nane", date(2026, 8, 8)),
    ("Nyerere Day", date(2026, 10, 14)),
    ("Independence Day", date(2026, 12, 9)),
    ("Christmas Day", date(2026, 12, 25)),
    ("Boxing Day", date(2026, 12, 26)),
]

SAMPLE_EMPLOYEES = [
    ("John", "Mwangi", "Sales Officer", "Sales", "PERMANENT", 850000),
    ("Grace", "Kimaro", "HR Officer", "HR & Admin", "PERMANENT", 1200000),
    ("Peter", "Msangi", "Storekeeper", "Procurement", "PERMANENT", 650000),
    ("Amina", "Hassan", "Logistics Officer", "Logistics", "CONTRACT", 750000),
    ("Joseph", "Macha", "Machine Operator", "Production", "PERMANENT", 550000),
]


class Command(BaseCommand):
    help = "Seed HR leave types, employees, and sample data"

    @transaction.atomic
    def handle(self, *args, **options):
        currency = Currency.objects.filter(is_default=True).first() or Currency.objects.first()
        if not currency:
            self.stdout.write(self.style.ERROR("No currency. Run seed_fms."))
            return

        CompanyProfile.objects.get_or_create(
            pk=1,
            defaults={
                "company_name": "Rock Solutions Limited",
                "tin": "127-950-695",
                "vat_number": "40022138R",
                "address": "Plot 252 Block L, Misungwi, Mwanza",
                "phone": "+255 28 250 0000",
                "email": "info@rocksolutions.co.tz",
            },
        )
        WorkingHoursConfig.objects.get_or_create(pk=1, defaults={"hours_per_day": Decimal("8")})

        for code, name, days, paid, carry in LEAVE_TYPES:
            LeaveType.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "days_entitled": days,
                    "is_paid": paid,
                    "carry_forward": carry,
                },
            )
        self.stdout.write("  Leave types seeded")

        AllowanceConfig.objects.update_or_create(
            name="Housing Allowance",
            defaults={"amount": Decimal("150000"), "is_taxable": True},
        )
        AllowanceConfig.objects.update_or_create(
            name="Transport Allowance",
            defaults={"amount": Decimal("80000"), "is_taxable": False},
        )

        year = timezone.now().year
        for name, hdate in TZ_HOLIDAYS_2026:
            PublicHoliday.objects.update_or_create(
                name=name, year=hdate.year,
                defaults={"date": hdate, "is_variable": False},
            )

        today = timezone.now().date()
        for first, last, title, dept_name, emp_type, salary in SAMPLE_EMPLOYEES:
            dept = Department.objects.filter(name=dept_name).first()
            if not dept:
                dept = Department.objects.filter(name__icontains=dept_name.split()[0]).first()
            if not dept:
                continue
            emp, created = Employee.objects.update_or_create(
                first_name=first,
                last_name=last,
                department=dept,
                defaults={
                    "employee_number": f"RSL-EMP-{Employee.objects.count() + 1:03d}",
                    "job_title": title,
                    "employment_type": emp_type,
                    "contract_start": today - timedelta(days=365),
                    "contract_end": today + timedelta(days=180) if emp_type == "CONTRACT" else None,
                    "basic_salary": Decimal(str(salary)),
                    "currency": currency,
                    "phone": f"+255 7{Employee.objects.count():02d} 000 000",
                    "national_id": f"19850{Employee.objects.count():06d}",
                    "tin_number": "127-950-695",
                    "nssf_number": f"NSSF{Employee.objects.count():06d}",
                    "nhif_number": f"NHIF{Employee.objects.count():06d}",
                    "status": Employee.STATUS_ACTIVE,
                    "gender": Employee.GENDER_MALE if first in ("John", "Peter", "Joseph") else Employee.GENDER_FEMALE,
                },
            )
            if created:
                EmployeeAllowance.objects.get_or_create(
                    employee=emp,
                    name="Transport Allowance",
                    defaults={"amount": Decimal("80000"), "is_taxable": False},
                )
                Attendance.objects.get_or_create(
                    employee=emp,
                    date=today,
                    defaults={"status": Attendance.STATUS_PRESENT, "hours_worked": Decimal("8")},
                )

        annual = LeaveType.objects.filter(code="ANNUAL").first()
        emp = Employee.objects.first()
        if annual and emp:
            LeaveRequest.objects.get_or_create(
                employee=emp,
                leave_type=annual,
                start_date=today + timedelta(days=30),
                defaults={
                    "end_date": today + timedelta(days=34),
                    "days_requested": 5,
                    "reason": "Family visit",
                    "status": LeaveRequest.STATUS_PENDING,
                },
            )

        self.stdout.write(self.style.SUCCESS("HR seed complete."))
