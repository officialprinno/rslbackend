"""HR API viewsets."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import HasModulePermission, user_has_permission
from apps.core.responses import api_error, api_response
from apps.hr.filters import (
    AppraisalFilter,
    AttendanceFilter,
    DisciplinaryFilter,
    EmployeeFilter,
    LeaveRequestFilter,
    PayrollFilter,
)
from apps.hr.mixins import HRViewSetMixin
from apps.hr.models import (
    AllowanceConfig,
    Appraisal,
    Attendance,
    CompanyProfile,
    DisciplinaryRecord,
    Employee,
    LeaveRequest,
    LeaveType,
    Payroll,
    PayrollItem,
    PublicHoliday,
    WorkingHoursConfig,
)
from apps.hr.serializers import (
    AllowanceConfigSerializer,
    AppraisalSerializer,
    AttendanceSerializer,
    CompanyProfileSerializer,
    DisciplinaryRecordSerializer,
    EmployeeListSerializer,
    EmployeeSerializer,
    LeaveRequestSerializer,
    LeaveTypeSerializer,
    PayrollItemSerializer,
    PayrollSerializer,
    PayslipSerializer,
    PublicHolidaySerializer,
    WorkingHoursConfigSerializer,
)
from apps.hr.services import HRService


class HRDashboardViewSet(HRViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        return api_response(data=HRService.dashboard())


class EmployeeViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = Employee.objects.select_related(
        "department", "currency", "reports_to", "user"
    ).prefetch_related("allowances", "documents")
    filterset_class = EmployeeFilter
    search_fields = ["first_name", "last_name", "employee_number", "national_id"]
    ordering_fields = ["employee_number", "last_name", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return EmployeeListSerializer
        return EmployeeSerializer

    def get_create_message(self):
        return "Employee created"

    def get_update_message(self):
        return "Employee updated"

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        emp = self.get_object()
        emp.status = Employee.STATUS_INACTIVE
        emp.is_active = False
        emp.resignation_date = timezone.now().date()
        emp.save()
        return api_response(
            data=EmployeeSerializer(emp).data,
            message="Employee deactivated",
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        emp = self.get_object()
        emp.status = Employee.STATUS_ACTIVE
        emp.is_active = True
        emp.resignation_date = None
        emp.save()
        return api_response(
            data=EmployeeSerializer(emp).data,
            message="Employee activated",
        )

    @action(detail=True, methods=["get"])
    def payslips(self, request, pk=None):
        items = PayrollItem.objects.filter(
            employee_id=pk, payroll__status=Payroll.STATUS_PAID
        ).select_related("employee", "payroll")
        return api_response(data=PayslipSerializer(items, many=True).data)


class AttendanceViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = Attendance.objects.select_related("employee", "employee__department")
    serializer_class = AttendanceSerializer
    filterset_class = AttendanceFilter
    ordering_fields = ["date"]

    @action(detail=False, methods=["post"], url_path="bulk-mark")
    def bulk_mark(self, request):
        records = request.data.get("records", [])
        created = []
        for rec in records:
            att, _ = Attendance.objects.update_or_create(
                employee_id=rec["employee"],
                date=rec["date"],
                defaults={
                    "status": rec.get("status", Attendance.STATUS_PRESENT),
                    "time_in": rec.get("time_in"),
                    "time_out": rec.get("time_out"),
                    "hours_worked": rec.get("hours_worked", 0),
                    "notes": rec.get("notes", ""),
                    "marked_by": request.user,
                },
            )
            created.append(AttendanceSerializer(att).data)
        return api_response(data=created, message="Attendance saved")

    @action(detail=False, methods=["get"], url_path="monthly-summary")
    def monthly_summary(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        employees = Employee.objects.filter(status=Employee.STATUS_ACTIVE, is_active=True)
        summary = []
        for emp in employees:
            qs = Attendance.objects.filter(employee=emp, date__month=month, date__year=year)
            total = qs.count()
            present = qs.filter(status=Attendance.STATUS_PRESENT).count()
            absent = qs.filter(status=Attendance.STATUS_ABSENT).count()
            late = qs.filter(status=Attendance.STATUS_LATE).count()
            leave = qs.filter(status=Attendance.STATUS_LEAVE).count()
            pct = round(present / total * 100, 1) if total else 0
            summary.append({
                "employee_id": emp.id,
                "employee_name": emp.full_name,
                "working_days": total,
                "present": present,
                "absent": absent,
                "late": late,
                "leave": leave,
                "attendance_percent": pct,
            })
        return api_response(data=summary)


class LeaveTypeViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    search_fields = ["name", "code"]


class LeaveRequestViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.select_related(
        "employee", "employee__department", "leave_type", "approved_by"
    )
    serializer_class = LeaveRequestSerializer
    filterset_class = LeaveRequestFilter
    ordering_fields = ["created_at", "start_date"]

    @action(detail=False, methods=["get"])
    def balances(self, request):
        employee_id = request.query_params.get("employee")
        if employee_id:
            emp = Employee.objects.filter(pk=employee_id).first()
            if not emp:
                return api_error(message="Employee not found.")
            return api_response(data=HRService.leave_balance(emp))
        result = []
        for emp in Employee.objects.filter(status=Employee.STATUS_ACTIVE, is_active=True):
            result.append({
                "employee_id": emp.id,
                "employee_name": emp.full_name,
                "department_name": emp.department.name,
                "balances": HRService.leave_balance(emp),
            })
        return api_response(data=result)

    @action(detail=False, methods=["get"])
    def calendar(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        leaves = LeaveRequest.objects.filter(
            status=LeaveRequest.STATUS_APPROVED,
            start_date__month=month,
            start_date__year=year,
        ).select_related("employee", "leave_type")
        data = [
            {
                "employee_name": lr.employee.full_name,
                "leave_type": lr.leave_type.name,
                "leave_type_code": lr.leave_type.code,
                "start_date": lr.start_date.isoformat(),
                "end_date": lr.end_date.isoformat(),
            }
            for lr in leaves
        ]
        return api_response(data=data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        lr = self.get_object()
        if lr.status != LeaveRequest.STATUS_PENDING:
            return api_error(message="Leave request is not pending.")
        balances = HRService.leave_balance(lr.employee, lr.leave_type)
        remaining = balances[0]["days_remaining"] if balances else 0
        if lr.days_requested > remaining:
            return api_error(message=f"Insufficient balance. Available: {remaining} days.")
        lr.status = LeaveRequest.STATUS_APPROVED
        lr.approved_by = request.user
        lr.approved_at = timezone.now()
        lr.save()
        return api_response(data=LeaveRequestSerializer(lr).data, message="Leave approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        lr = self.get_object()
        reason = request.data.get("reason", "")
        if not reason:
            return api_error(message="Rejection reason is required.")
        lr.status = LeaveRequest.STATUS_REJECTED
        lr.rejection_reason = reason
        lr.approved_by = request.user
        lr.approved_at = timezone.now()
        lr.save()
        return api_response(data=LeaveRequestSerializer(lr).data, message="Leave rejected")


class PayrollViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = Payroll.objects.select_related("department", "processed_by", "approved_by").prefetch_related(
        "items__employee"
    )
    serializer_class = PayrollSerializer
    filterset_class = PayrollFilter
    ordering_fields = ["period_year", "period_month"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "attendance_check"):

            class HasHrOrFinanceRead(IsAuthenticated):
                def has_permission(self, request, view):
                    if not super().has_permission(request, view):
                        return False
                    user = request.user
                    return user_has_permission(user, "hr", "read") or user_has_permission(
                        user, "finance", "read"
                    )

            return [HasHrOrFinanceRead()]

        if self.action in ("approve", "mark_paid"):
            self.module_name = "finance"
            self.required_action = "approve"
            return [IsAuthenticated(), HasModulePermission()]

        if self.action in ("submit", "generate", "update_item"):
            self.module_name = "hr"
            self.required_action = "update" if self.action == "submit" else "create"
            return [IsAuthenticated(), HasModulePermission()]

        return super().get_permissions()

    @action(detail=False, methods=["post"])
    def generate(self, request):
        month = int(request.data.get("period_month", timezone.now().month))
        year = int(request.data.get("period_year", timezone.now().year))
        dept = request.data.get("department")
        try:
            payroll = HRService.generate_payroll(month, year, dept, request.user)
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(
            data=PayrollSerializer(payroll).data,
            message="Payroll generated",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="attendance-check")
    def attendance_check(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        dept = request.query_params.get("department")
        return api_response(data=HRService.attendance_verification(month, year, dept))

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        payroll = self.get_object()
        if payroll.status != Payroll.STATUS_DRAFT:
            return api_error(message="Only draft payroll can be submitted for finance approval.")
        payroll.status = Payroll.STATUS_REVIEWED
        payroll.save(update_fields=["status", "updated_at"])
        HRService.notify_payroll_submitted(payroll)
        return api_response(
            data=PayrollSerializer(payroll).data,
            message="Payroll submitted to Finance for approval",
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        payroll = self.get_object()
        if payroll.status != Payroll.STATUS_REVIEWED:
            return api_error(message="Only payroll awaiting finance review can be approved.")
        payroll.status = Payroll.STATUS_APPROVED
        payroll.approved_by = request.user
        payroll.approved_at = timezone.now()
        payroll.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        HRService.notify_payroll_approved(payroll, request.user)
        return api_response(
            data=PayrollSerializer(payroll).data,
            message="Payroll approved",
        )

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        payroll = self.get_object()
        if payroll.status != Payroll.STATUS_APPROVED:
            return api_error(message="Only approved payroll can be marked as paid.")
        payroll.status = Payroll.STATUS_PAID
        payroll.paid_at = timezone.now()
        payroll.save(update_fields=["status", "paid_at", "updated_at"])
        return api_response(data=PayrollSerializer(payroll).data, message="Payroll marked as paid")

    @action(detail=True, methods=["post"], url_path="update-item")
    def update_item(self, request, pk=None):
        item_id = request.data.get("item_id")
        payroll = self.get_object()
        item = payroll.items.filter(pk=item_id).first()
        if not item:
            return api_error(message="Payroll item not found.")
        calc = HRService.calculate_payroll_item(item.employee, request.data)
        for field, val in calc.items():
            if field == "allowances":
                item.allowances_json = val
            elif hasattr(item, field):
                setattr(item, field, val)
        item.save()
        return api_response(data=PayrollItemSerializer(item).data, message="Item updated")


class PayslipViewSet(HRViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PayrollItem.objects.filter(
        payroll__status=Payroll.STATUS_PAID
    ).select_related("employee", "payroll")
    serializer_class = PayslipSerializer
    filterset_fields = ["employee", "payroll"]
    ordering_fields = ["payroll__period_year", "payroll__period_month"]


class AllowanceConfigViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = AllowanceConfig.objects.select_related("department")
    serializer_class = AllowanceConfigSerializer
    search_fields = ["name"]


class AppraisalViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = Appraisal.objects.select_related("employee", "reviewer")
    serializer_class = AppraisalSerializer
    filterset_class = AppraisalFilter
    ordering_fields = ["scheduled_date"]

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        from apps.hr.payroll_utils import appraisal_rating

        appraisal = self.get_object()
        score = request.data.get("score")
        appraisal.score = score
        appraisal.rating = appraisal_rating(score) if score is not None else ""
        appraisal.strengths = request.data.get("strengths", "")
        appraisal.improvements = request.data.get("improvements", "")
        appraisal.goals = request.data.get("goals", "")
        appraisal.comments = request.data.get("comments", "")
        appraisal.employee_acknowledged = request.data.get("employee_acknowledged", False)
        appraisal.status = Appraisal.STATUS_COMPLETED
        appraisal.completed_at = timezone.now()
        appraisal.save()
        return api_response(data=AppraisalSerializer(appraisal).data, message="Appraisal completed")


class DisciplinaryRecordViewSet(HRViewSetMixin, viewsets.ModelViewSet):
    queryset = DisciplinaryRecord.objects.select_related("employee", "issued_by")
    serializer_class = DisciplinaryRecordSerializer
    filterset_class = DisciplinaryFilter
    ordering_fields = ["incident_date"]

    def perform_create(self, serializer):
        serializer.save(issued_by=self.request.user)


class HRAdminViewSet(HRViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get", "patch"], url_path="company-profile")
    def company_profile(self, request):
        profile, _ = CompanyProfile.objects.get_or_create(pk=1)
        if request.method == "GET":
            return api_response(data=CompanyProfileSerializer(profile).data)
        serializer = CompanyProfileSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        return api_response(data=serializer.data, message="Profile updated")

    @action(detail=False, methods=["get", "patch"], url_path="working-hours")
    def working_hours(self, request):
        config, _ = WorkingHoursConfig.objects.get_or_create(pk=1)
        if request.method == "GET":
            return api_response(data=WorkingHoursConfigSerializer(config).data)
        serializer = WorkingHoursConfigSerializer(config, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        return api_response(data=serializer.data, message="Working hours updated")

    @action(detail=False, methods=["get", "post"], url_path="public-holidays")
    def holidays(self, request):
        year = int(request.query_params.get("year", timezone.now().year))
        if request.method == "GET":
            qs = PublicHoliday.objects.filter(year=year, is_active=True)
            return api_response(data=PublicHolidaySerializer(qs, many=True).data)
        serializer = PublicHolidaySerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        return api_response(data=serializer.data, message="Holiday added", status=status.HTTP_201_CREATED)
