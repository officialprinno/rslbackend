"""Safety API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.safety.views import (
    PPEIssuanceViewSet,
    PPEItemViewSet,
    PPERequestViewSet,
    PPERoleRequirementViewSet,
    SafetyDashboardViewSet,
    SafetyIncidentViewSet,
    SafetyInspectionViewSet,
    SafetyReportViewSet,
    SafetyTrainingViewSet,
    WorkPermitViewSet,
)
from apps.safety.security_views import (
    AccessLogViewSet,
    AccessZoneViewSet,
    InterLocationMovementViewSet,
    SecurityDashboardViewSet,
    SecurityIncidentViewSet,
    SecurityLocationViewSet,
    SecurityPersonnelViewSet,
    SecurityShiftViewSet,
    VehicleLogViewSet,
    VisitorViewSet,
)

router = DefaultRouter()
router.register("dashboard", SafetyDashboardViewSet, basename="safety-dashboard")
router.register("incidents", SafetyIncidentViewSet, basename="safety-incident")
router.register("inspections", SafetyInspectionViewSet, basename="safety-inspection")
router.register("ppe-requests", PPERequestViewSet, basename="ppe-request")
router.register("ppe-items", PPEItemViewSet, basename="ppe-item")
router.register("ppe-issuances", PPEIssuanceViewSet, basename="ppe-issuance")
router.register("ppe-requirements", PPERoleRequirementViewSet, basename="ppe-requirement")
router.register("permits", WorkPermitViewSet, basename="work-permit")
router.register("training", SafetyTrainingViewSet, basename="safety-training")
router.register("reports", SafetyReportViewSet, basename="safety-report")

# Security sub-department
router.register("security/locations", SecurityLocationViewSet, basename="security-location")
router.register("security/dashboard", SecurityDashboardViewSet, basename="security-dashboard")
router.register("security/visitors", VisitorViewSet, basename="security-visitor")
router.register("security/vehicles", VehicleLogViewSet, basename="security-vehicle")
router.register("security/movements", InterLocationMovementViewSet, basename="security-movement")
router.register("security/personnel", SecurityPersonnelViewSet, basename="security-personnel")
router.register("security/shifts", SecurityShiftViewSet, basename="security-shift")
router.register("security/zones", AccessZoneViewSet, basename="security-zone")
router.register("security/access-logs", AccessLogViewSet, basename="security-access-log")
router.register("security/incidents", SecurityIncidentViewSet, basename="security-incident")

urlpatterns = [
    path("", include(router.urls)),
]
