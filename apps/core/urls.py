"""Core URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.core.views import AuditLogViewSet, CurrencyViewSet, MultiDepartmentDashboardView

router = DefaultRouter()
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/multi-department/", MultiDepartmentDashboardView.as_view(), name="multi-dept-dashboard"),
]
