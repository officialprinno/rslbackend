"""Logistics API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.logistics.views import (
    DeliveryNoteViewSet,
    DeliveryOrderViewSet,
    DriverViewSet,
    FuelRecordViewSet,
    LogisticsDashboardViewSet,
    MaintenanceViewSet,
    SalesOrderLogisticsViewSet,
    VehicleViewSet,
)
from apps.logistics.driver_portal_views import DriverPortalViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("drivers", DriverViewSet, basename="driver")
router.register("deliveries", DeliveryOrderViewSet, basename="delivery-order")
router.register("delivery-notes", DeliveryNoteViewSet, basename="delivery-note")
router.register("maintenance", MaintenanceViewSet, basename="maintenance")
router.register("fuel", FuelRecordViewSet, basename="fuel")
router.register("dashboard", LogisticsDashboardViewSet, basename="logistics-dashboard")
router.register("sales-orders", SalesOrderLogisticsViewSet, basename="logistics-sales-order")
router.register("driver-portal", DriverPortalViewSet, basename="driver-portal")

urlpatterns = [
    path("", include(router.urls)),
]
