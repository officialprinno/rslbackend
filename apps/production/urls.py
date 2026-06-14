"""Production API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.production.views import (
    BOMViewSet,
    MachineUsageViewSet,
    MachineViewSet,
    OutputRecordViewSet,
    ProductViewSet,
    ProductionDashboardViewSet,
    ProductionReportsView,
    WorkOrderViewSet,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("bom", BOMViewSet, basename="bom")
router.register("work-orders", WorkOrderViewSet, basename="work-order")
router.register("output", OutputRecordViewSet, basename="output")
router.register("machines", MachineViewSet, basename="machine")
router.register("machine-usage", MachineUsageViewSet, basename="machine-usage")
router.register("dashboard", ProductionDashboardViewSet, basename="production-dashboard")

urlpatterns = [
    path("reports/", ProductionReportsView.as_view(), name="production-reports"),
    path("", include(router.urls)),
]
