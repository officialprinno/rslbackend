"""HR API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.hr.views import (
    AllowanceConfigViewSet,
    AppraisalViewSet,
    AttendanceViewSet,
    DisciplinaryRecordViewSet,
    EmployeeViewSet,
    HRAdminViewSet,
    HRDashboardViewSet,
    LeaveRequestViewSet,
    LeaveTypeViewSet,
    PayrollViewSet,
    PayslipViewSet,
)

router = DefaultRouter()
router.register("dashboard", HRDashboardViewSet, basename="hr-dashboard")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("leave-types", LeaveTypeViewSet, basename="leave-type")
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register("payrolls", PayrollViewSet, basename="payroll")
router.register("payslips", PayslipViewSet, basename="payslip")
router.register("allowances", AllowanceConfigViewSet, basename="allowance")
router.register("appraisals", AppraisalViewSet, basename="appraisal")
router.register("disciplinary", DisciplinaryRecordViewSet, basename="disciplinary")
router.register("admin", HRAdminViewSet, basename="hr-admin")

urlpatterns = [
    path("", include(router.urls)),
]
