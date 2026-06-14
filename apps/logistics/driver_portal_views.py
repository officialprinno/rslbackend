"""Driver portal API — scoped to the logged-in driver's assignments."""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import user_has_permission
from apps.core.responses import api_error, api_response
from apps.logistics.driver_portal_serializers import (
    ArrivalSerializer,
    ConfirmDeliverySerializer,
    ConfirmReturnSerializer,
    DriverDashboardSerializer,
    DriverProfileSerializer,
    DriverTripSerializer,
    StartDeliverySerializer,
    StartReturnSerializer,
    VehicleConditionSerializer,
)
from apps.logistics.driver_portal_service import DriverPortalService
from apps.logistics.models import DeliveryOrder, Driver
from apps.logistics.serializers import VehicleSerializer


class IsDriverOrPortalUser(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if hasattr(request.user, "driver_profile"):
            return request.user.driver_profile.is_active
        return user_has_permission(request.user, "driver_portal", "read")


class DriverPortalViewSet(viewsets.ViewSet):
    permission_classes = [IsDriverOrPortalUser]

    def _driver(self, request) -> Driver:
        return DriverPortalService.get_driver_for_user(request.user)

    def _trip_qs(self, driver: Driver):
        return (
            DeliveryOrder.objects.filter(driver=driver, is_active=True)
            .select_related("sales_order", "customer", "vehicle", "origin_warehouse")
            .prefetch_related("items__item", "trip_events__user", "confirmation")
        )

    @action(detail=False, methods=["get"])
    def profile(self, request):
        driver = self._driver(request)
        return api_response(data=DriverProfileSerializer(driver).data)

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        driver = self._driver(request)
        data = DriverPortalService.driver_dashboard(driver)
        return api_response(data=DriverDashboardSerializer(data).data)

    @action(detail=False, methods=["get"])
    def deliveries(self, request):
        driver = self._driver(request)
        qs = self._trip_qs(driver)
        status_filter = request.query_params.get("status")
        if status_filter == "assigned":
            qs = qs.filter(trip_status=DeliveryOrder.TRIP_ASSIGNED)
        elif status_filter == "active":
            qs = qs.filter(
                trip_status__in=DriverPortalService.ACTIVE_TRIP_STATUSES
            ).exclude(trip_status=DeliveryOrder.TRIP_RETURN_CONFIRMED)
        elif status_filter == "completed":
            qs = qs.filter(trip_status=DeliveryOrder.TRIP_RETURN_CONFIRMED)
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(do_number__icontains=search)
        return api_response(
            data=DriverTripSerializer(qs.order_by("-scheduled_date")[:100], many=True).data
        )

    @action(detail=False, methods=["get"], url_path=r"trips/(?P<trip_id>[^/.]+)")
    def trip_detail(self, request, trip_id=None):
        driver = self._driver(request)
        order = self._trip_qs(driver).filter(pk=trip_id).first()
        if not order:
            return api_error(message="Trip not found.", status=404)
        return api_response(data=DriverTripSerializer(order).data)

    @action(detail=False, methods=["post"], url_path=r"trips/(?P<trip_id>[^/.]+)/start")
    def start_trip(self, request, trip_id=None):
        driver = self._driver(request)
        order = self._trip_qs(driver).filter(pk=trip_id).first()
        if not order:
            return api_error(message="Trip not found.", status=404)
        ser = StartDeliverySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = DriverPortalService.start_delivery(
            order, driver, request.user,
            ser.validated_data["odometer_start"],
            ser.validated_data.get("vehicle_condition", "GOOD"),
        )
        return api_response(data=DriverTripSerializer(order).data, message="Delivery started")

    @action(detail=False, methods=["post"], url_path=r"trips/(?P<trip_id>[^/.]+)/arrive")
    def arrive(self, request, trip_id=None):
        driver = self._driver(request)
        order = self._trip_qs(driver).filter(pk=trip_id).first()
        if not order:
            return api_error(message="Trip not found.", status=404)
        ser = ArrivalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = DriverPortalService.confirm_arrival(
            order, driver, request.user, ser.validated_data.get("notes", "")
        )
        return api_response(data=DriverTripSerializer(order).data, message="Arrival confirmed")

    @action(detail=False, methods=["post"], url_path=r"trips/(?P<trip_id>[^/.]+)/confirm-delivery")
    def confirm_delivery(self, request, trip_id=None):
        driver = self._driver(request)
        order = self._trip_qs(driver).filter(pk=trip_id).first()
        if not order:
            return api_error(message="Trip not found.", status=404)
        ser = ConfirmDeliverySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = DriverPortalService.confirm_delivery(
            order, driver, request.user, ser.validated_data
        )
        return api_response(
            data=DriverTripSerializer(order).data,
            message="Delivery confirmed — awaiting logistics review",
        )

    @action(detail=False, methods=["post"], url_path=r"trips/(?P<trip_id>[^/.]+)/start-return")
    def start_return(self, request, trip_id=None):
        driver = self._driver(request)
        order = self._trip_qs(driver).filter(pk=trip_id).first()
        if not order:
            return api_error(message="Trip not found.", status=404)
        ser = StartReturnSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = DriverPortalService.start_return(
            order, driver, request.user,
            ser.validated_data.get("vehicle_condition", "GOOD"),
        )
        return api_response(data=DriverTripSerializer(order).data, message="Return trip started")

    @action(detail=False, methods=["post"], url_path=r"trips/(?P<trip_id>[^/.]+)/confirm-return")
    def confirm_return(self, request, trip_id=None):
        driver = self._driver(request)
        order = self._trip_qs(driver).filter(pk=trip_id).first()
        if not order:
            return api_error(message="Trip not found.", status=404)
        ser = ConfirmReturnSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = DriverPortalService.confirm_return(
            order, driver, request.user,
            ser.validated_data["odometer_end"],
            ser.validated_data.get("fuel_remaining"),
            ser.validated_data.get("vehicle_condition", "GOOD"),
        )
        return api_response(
            data=DriverTripSerializer(order).data,
            message="Return confirmed — you are now available",
        )

    @action(detail=False, methods=["post"], url_path="vehicle-condition")
    def vehicle_condition(self, request):
        driver = self._driver(request)
        ser = VehicleConditionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        report = DriverPortalService.report_vehicle_condition(
            driver, request.user, ser.validated_data
        )
        return api_response(
            data={"id": report.id, "condition": report.condition},
            message="Vehicle condition reported",
        )

    @action(detail=False, methods=["get"])
    def history(self, request):
        driver = self._driver(request)
        qs = self._trip_qs(driver).filter(
            trip_status__in=(
                DeliveryOrder.TRIP_RETURN_CONFIRMED,
                DeliveryOrder.TRIP_DELIVERED,
            )
        ).order_by("-delivered_at", "-scheduled_date")[:50]
        return api_response(data=DriverTripSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def reports(self, request):
        driver = self._driver(request)
        perf = DriverPortalService.driver_performance(driver)
        vehicle = driver.assigned_vehicle
        vehicle_data = VehicleSerializer(vehicle).data if vehicle else None
        return api_response(data={"performance": perf, "vehicle": vehicle_data})

    @action(detail=False, methods=["post"], url_path="draft")
    def save_draft(self, request):
        draft_key = request.data.get("key", "default")
        draft_data = request.data.get("data", {})
        request.session[f"driver_draft_{draft_key}"] = draft_data
        request.session.modified = True
        return api_response(data={"saved": True, "key": draft_key})

    @action(detail=False, methods=["get"], url_path=r"draft/(?P<draft_key>[^/.]+)")
    def load_draft(self, request, draft_key="default"):
        data = request.session.get(f"driver_draft_{draft_key}", {})
        return api_response(data={"key": draft_key, "data": data})
