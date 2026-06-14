"""HR business logic."""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.models import Currency
from apps.hr.models import (
    Attendance,
    Employee,
    LeaveRequest,
    LeaveType,
    Payroll,
    PayrollItem,
    PublicHoliday,
)
from apps.hr.payroll_utils import (
    appraisal_rating,
    calculate_nhif,
    calculate_nssf,
    calculate_paye,
    count_working_days,
)
from apps.hr.utils import generate_employee_number, generate_payroll_number, work_email_from_name
from apps.messaging.models import AppNotification

MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class HRService:
    @staticmethod
    def leave_balance(employee, leave_type=None):
        types = [leave_type] if leave_type else LeaveType.objects.filter(is_active=True)
        balances = []
        for lt in types:
            used = LeaveRequest.objects.filter(
                employee=employee,
                leave_type=lt,
                status=LeaveRequest.STATUS_APPROVED,
            ).aggregate(total=Sum("days_requested"))["total"] or 0
            balances.append(
                {
                    "leave_type_id": lt.id,
                    "leave_type_name": lt.name,
                    "days_entitled": lt.days_entitled,
                    "days_used": used,
                    "days_remaining": max(lt.days_entitled - used, 0),
                    "is_paid": lt.is_paid,
                }
            )
        return balances

    @staticmethod
    def dashboard():
        today = timezone.now().date()
        month_start = today.replace(day=1)
        active_employees = Employee.objects.filter(
            status=Employee.STATUS_ACTIVE, is_active=True
        )
        total = active_employees.count()

        present_today = Attendance.objects.filter(
            date=today, status=Attendance.STATUS_PRESENT
        ).count()
        on_leave_today = Attendance.objects.filter(
            date=today, status=Attendance.STATUS_LEAVE
        ).count()
        new_joiners = Employee.objects.filter(
            contract_start__gte=month_start, status=Employee.STATUS_ACTIVE
        ).count()
        resignations = Employee.objects.filter(
            resignation_date__gte=month_start
        ).count()
        pending_leave = LeaveRequest.objects.filter(
            status=LeaveRequest.STATUS_PENDING
        ).count()

        by_dept = (
            active_employees.values("department__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        by_type = (
            active_employees.values("employment_type")
            .annotate(count=Count("id"))
        )

        attendance_summary = []
        for dept in by_dept:
            dept_name = dept["department__name"]
            dept_emps = active_employees.filter(department__name=dept_name)
            dept_total = dept_emps.count()
            att_qs = Attendance.objects.filter(
                date=today, employee__in=dept_emps
            )
            attendance_summary.append(
                {
                    "department": dept_name,
                    "total": dept_total,
                    "present": att_qs.filter(status=Attendance.STATUS_PRESENT).count(),
                    "absent": att_qs.filter(status=Attendance.STATUS_ABSENT).count(),
                    "on_leave": att_qs.filter(status=Attendance.STATUS_LEAVE).count(),
                    "late": att_qs.filter(status=Attendance.STATUS_LATE).count(),
                }
            )

        alerts = []
        expiry_cutoff = today + timedelta(days=30)
        for emp in active_employees.filter(
            contract_end__isnull=False,
            contract_end__lte=expiry_cutoff,
            contract_end__gte=today,
        ):
            days = (emp.contract_end - today).days
            alerts.append(
                {
                    "type": "CONTRACT_EXPIRY",
                    "severity": "MEDIUM" if days > 14 else "HIGH",
                    "employee_id": emp.id,
                    "employee_name": emp.full_name,
                    "message": f"Contract expires in {days} days",
                    "date": emp.contract_end.isoformat(),
                    "days_remaining": days,
                }
            )

        probation_cutoff = today + timedelta(days=7)
        for emp in active_employees.filter(
            probation_end__isnull=False,
            probation_end__lte=probation_cutoff,
            probation_end__gte=today,
        ):
            days = (emp.probation_end - today).days
            alerts.append(
                {
                    "type": "PROBATION_END",
                    "severity": "LOW",
                    "employee_id": emp.id,
                    "employee_name": emp.full_name,
                    "message": f"Probation ends in {days} days",
                    "date": emp.probation_end.isoformat(),
                    "days_remaining": days,
                }
            )

        for lr in LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING)[:10]:
            alerts.append(
                {
                    "type": "LEAVE_PENDING",
                    "severity": "MEDIUM",
                    "employee_id": lr.employee_id,
                    "employee_name": lr.employee.full_name,
                    "message": f"Pending {lr.leave_type.name} leave request",
                    "date": lr.start_date.isoformat(),
                    "days_remaining": 0,
                }
            )

        upcoming = [
            {
                "title": "Payroll Processing",
                "date": (month_start + timedelta(days=27)).isoformat(),
                "type": "PAYROLL",
            },
        ]

        return {
            "total_employees": total,
            "present_today": present_today,
            "on_leave_today": on_leave_today,
            "new_joiners_month": new_joiners,
            "resignations_month": resignations,
            "pending_leave_requests": pending_leave,
            "employees_by_department": [
                {"department": d["department__name"], "count": d["count"]} for d in by_dept
            ],
            "employment_type_breakdown": [
                {"type": t["employment_type"], "count": t["count"]} for t in by_type
            ],
            "attendance_summary": attendance_summary,
            "alerts": alerts,
            "upcoming_events": upcoming,
        }

    @staticmethod
    def calculate_payroll_item(employee, overrides=None):
        overrides = overrides or {}
        basic = Decimal(str(overrides.get("basic_salary", employee.basic_salary)))
        allowances = []
        total_allowances = Decimal("0")
        for a in employee.allowances.filter(is_active=True):
            amt = Decimal(str(a.amount))
            allowances.append(
                {"name": a.name, "amount": str(amt), "is_taxable": a.is_taxable}
            )
            total_allowances += amt

        gross = basic + total_allowances
        nssf = calculate_nssf(basic)
        paye = calculate_paye(float(gross)) if employee.paye_applicable else 0
        nhif = calculate_nhif(float(gross))
        other = Decimal(str(overrides.get("other_deductions", 0)))
        total_ded = Decimal(nssf["employee"] + paye + nhif) + other
        net = gross - total_ded

        return {
            "basic_salary": str(basic),
            "allowances": allowances,
            "total_allowances": str(total_allowances),
            "gross_salary": str(gross),
            "nssf_employee": str(nssf["employee"]),
            "nssf_employer": str(nssf["employer"]),
            "paye": str(paye),
            "nhif": str(nhif),
            "other_deductions": str(other),
            "total_deductions": str(total_ded),
            "net_salary": str(net),
        }

    @staticmethod
    @transaction.atomic
    def generate_payroll(month, year, department_id=None, user=None):
        employees = Employee.objects.filter(
            status=Employee.STATUS_ACTIVE, is_active=True
        )
        if department_id:
            employees = employees.filter(department_id=department_id)

        payroll, created = Payroll.objects.get_or_create(
            period_month=month,
            period_year=year,
            department_id=department_id,
            defaults={
                "payroll_number": generate_payroll_number(year),
                "processed_by": user,
            },
        )
        if not created and payroll.status != Payroll.STATUS_DRAFT:
            raise ValueError("Payroll for this period already processed.")

        payroll.items.all().delete()
        totals = {
            "gross": Decimal("0"),
            "nssf_e": Decimal("0"),
            "nssf_er": Decimal("0"),
            "paye": Decimal("0"),
            "nhif": Decimal("0"),
            "deductions": Decimal("0"),
            "net": Decimal("0"),
        }

        for emp in employees:
            calc = HRService.calculate_payroll_item(emp)
            PayrollItem.objects.create(
                payroll=payroll,
                employee=emp,
                basic_salary=calc["basic_salary"],
                allowances_json=calc["allowances"],
                total_allowances=calc["total_allowances"],
                gross_salary=calc["gross_salary"],
                nssf_employee=calc["nssf_employee"],
                nssf_employer=calc["nssf_employer"],
                paye=calc["paye"],
                nhif=calc["nhif"],
                total_deductions=calc["total_deductions"],
                net_salary=calc["net_salary"],
            )
            totals["gross"] += Decimal(calc["gross_salary"])
            totals["nssf_e"] += Decimal(calc["nssf_employee"])
            totals["nssf_er"] += Decimal(calc["nssf_employer"])
            totals["paye"] += Decimal(calc["paye"])
            totals["nhif"] += Decimal(calc["nhif"])
            totals["deductions"] += Decimal(calc["total_deductions"])
            totals["net"] += Decimal(calc["net_salary"])

        payroll.total_employees = employees.count()
        payroll.total_gross = totals["gross"]
        payroll.total_nssf_employee = totals["nssf_e"]
        payroll.total_nssf_employer = totals["nssf_er"]
        payroll.total_paye = totals["paye"]
        payroll.total_nhif = totals["nhif"]
        payroll.total_deductions = totals["deductions"]
        payroll.total_net = totals["net"]
        payroll.processed_by = user
        payroll.save()
        return payroll

    @staticmethod
    def attendance_verification(month, year, department_id=None):
        employees = Employee.objects.filter(
            status=Employee.STATUS_ACTIVE, is_active=True
        )
        if department_id:
            employees = employees.filter(department_id=department_id)
        total = employees.count()
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        recorded = (
            Attendance.objects.filter(
                employee__in=employees,
                date__gte=start,
                date__lte=end,
            )
            .values("employee_id")
            .distinct()
            .count()
        )
        return {"total": total, "verified": recorded, "complete": recorded >= total}

    @staticmethod
    def prepare_employee(validated_data, allowances_data=None):
        if not validated_data.get("employee_number"):
            validated_data["employee_number"] = generate_employee_number()
        if not validated_data.get("work_email"):
            validated_data["work_email"] = work_email_from_name(
                validated_data.get("first_name"),
                validated_data.get("last_name"),
            )
        return validated_data

    @staticmethod
    def ensure_employee_for_user(
        user,
        *,
        job_title: str,
        department=None,
        basic_salary: Decimal | None = None,
        employment_type: str | None = None,
        status: str | None = None,
    ) -> Employee | None:
        """
        Ensure an HR Employee record exists for a system user (e.g. logistics driver).

        Links by user.employee_profile, then work_email, otherwise creates a new record.
        """
        if not user or not user.is_active:
            return None

        existing = getattr(user, "employee_profile", None)
        if existing:
            return existing

        dept = department or user.department
        if not dept:
            return None

        currency = Currency.objects.filter(is_default=True).first() or Currency.objects.first()
        if not currency:
            return None

        if user.email:
            linked = Employee.objects.filter(work_email__iexact=user.email).first()
            if linked:
                if not linked.user_id:
                    linked.user = user
                    linked.save(update_fields=["user", "updated_at"])
                return linked

        today = timezone.now().date()
        emp = Employee.objects.create(
            user=user,
            first_name=user.first_name or "Unknown",
            last_name=user.last_name or "User",
            department=dept,
            job_title=job_title,
            work_email=user.email or work_email_from_name(user.first_name, user.last_name),
            phone=user.phone or "",
            employment_type=employment_type or Employee.EMP_PERMANENT,
            contract_start=today,
            basic_salary=basic_salary if basic_salary is not None else Decimal("650000"),
            currency=currency,
            status=status or Employee.STATUS_ACTIVE,
            employee_number=generate_employee_number(),
        )
        return emp

    @staticmethod
    def ensure_user_for_employee(employee, *, role_name: str = "Driver"):
        """Link an HR employee to a portal user (create login if missing)."""
        from apps.users.models import Role, User

        if employee.user_id:
            user = employee.user
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active", "updated_at"])
            return user

        email = (employee.work_email or work_email_from_name(employee.first_name, employee.last_name)).strip().lower()
        if not email:
            raise ValueError("Employee needs a work email or valid name to create a login.")

        if User.objects.filter(email__iexact=email).exclude(pk=employee.user_id).exists():
            suffix = 1
            local, _, domain = email.partition("@")
            domain = domain or "rocksolutions.co.tz"
            while User.objects.filter(email__iexact=email).exists():
                email = f"{local}{suffix}@{domain}"
                suffix += 1

        dept = employee.department
        role = None
        if dept:
            role = Role.objects.filter(name=role_name, department=dept).first()
        if not role:
            role = Role.objects.filter(name=role_name, department__name="Logistics").first()

        user = User.objects.create(
            email=email,
            first_name=employee.first_name,
            last_name=employee.last_name,
            phone=employee.phone or "",
            department=dept,
            role=role,
            is_active=True,
        )
        user.set_unusable_password()
        user.save()

        employee.user = user
        if not employee.work_email:
            employee.work_email = email
        employee.save(update_fields=["user", "work_email", "updated_at"])
        return user

    @staticmethod
    def eligible_driver_employees():
        """Active HR employees who are not already registered as drivers."""
        from apps.logistics.models import Driver

        driver_user_ids = set(
            Driver.objects.filter(is_active=True).values_list("user_id", flat=True)
        )
        employees = (
            Employee.objects.filter(status=Employee.STATUS_ACTIVE, is_active=True)
            .select_related("user", "department")
            .order_by("last_name", "first_name")
        )
        eligible = []
        for emp in employees:
            if emp.user_id and emp.user_id in driver_user_ids:
                continue
            if emp.user and getattr(emp.user, "driver_profile", None):
                continue
            eligible.append(emp)
        return eligible

    @staticmethod
    def _payroll_period_label(payroll: Payroll) -> str:
        month = payroll.period_month
        name = MONTH_NAMES[month] if 1 <= month <= 12 else str(month)
        return f"{name} {payroll.period_year}"

    @staticmethod
    def notify_module_users(
        *,
        module: str,
        title: str,
        body: str,
        navigate_to: str,
        actions=("read",),
        reference_type: str = "",
        reference_id: int | None = None,
        notification_type=None,
        icon: str = "bell",
        color: str = "blue",
    ) -> None:
        from apps.messaging.models import AppNotification
        from apps.users.models import Permission, User

        if notification_type is None:
            notification_type = AppNotification.TYPE_ALERT

        role_ids = Permission.objects.filter(
            module=module,
            action__in=actions,
            is_active=True,
        ).values_list("role_id", flat=True)
        users = User.objects.filter(is_active=True, role_id__in=role_ids).distinct()
        for user in users[:50]:
            AppNotification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                body=body[:250],
                icon=icon,
                color=color,
                reference_type=reference_type or None,
                reference_id=reference_id,
                navigate_to=navigate_to,
            )

    @staticmethod
    def notify_payroll_submitted(payroll: Payroll) -> None:
        period = HRService._payroll_period_label(payroll)
        HRService.notify_module_users(
            module="finance",
            actions=("approve", "read"),
            title="Payroll pending finance approval",
            body=(
                f"HR submitted payroll {payroll.payroll_number} for {period}. "
                f"Net payable: TZS {payroll.total_net:,.0f}."
            ),
            navigate_to=f"/finance/payroll-approvals/{payroll.id}",
            reference_type="payroll",
            reference_id=payroll.id,
            notification_type=AppNotification.TYPE_APPROVAL,
            icon="currency",
            color="purple",
        )

    @staticmethod
    def notify_payroll_approved(payroll: Payroll, approved_by) -> None:
        period = HRService._payroll_period_label(payroll)
        approver = approved_by.get_full_name() or approved_by.email
        HRService.notify_module_users(
            module="hr",
            actions=("read", "update", "approve"),
            title="Payroll approved by Finance",
            body=(
                f"Finance approved payroll {payroll.payroll_number} for {period} "
                f"({approver}). You may mark it as paid when disbursement is complete."
            ),
            navigate_to=f"/hr/payroll/{payroll.id}",
            reference_type="payroll",
            reference_id=payroll.id,
            notification_type=AppNotification.TYPE_APPROVAL,
            icon="check",
            color="green",
        )
