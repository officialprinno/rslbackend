"""Logistics API viewsets."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.logistics.filters import (
    DeliveryNoteFilter,
    DeliveryOrderFilter,
    DriverFilter,
    FuelRecordFilter,
    MaintenanceFilter,
    VehicleFilter,
)
from apps.logistics.mixins import LogisticsViewSetMixin
from apps.logistics.models import (
    DeliveryNote,
    DeliveryOrder,
    Driver,
    FuelRecord,
    Vehicle,
    VehicleMaintenance,
)
from apps.logistics.serializers import (
    CompleteMaintenanceSerializer,
    DeliveredSerializer,
    DeliveryNoteSerializer,
    DeliveryOrderSerializer,
    DriverSerializer,
    FailedSerializer,
    FuelRecordSerializer,
    MaintenanceSerializer,
    SalesOrderLogisticsDetailSerializer,
    SalesOrderLogisticsSerializer,
    SignDeliveryNoteSerializer,
    VehicleSerializer,
)
from apps.logistics.services import LogisticsService
from apps.sales.models import SalesOrder


class VehicleViewSet(LogisticsViewSetMixin, viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    filterset_class = VehicleFilter
    search_fields = ["registration_number", "make", "model"]
    ordering_fields = ["registration_number", "next_service_date", "created_at"]

    def get_create_message(self):
        return "Vehicle created"

    def get_update_message(self):
        return "Vehicle updated"

    def get_destroy_message(self):
        return "Vehicle deactivated"

    def perform_create(self, serializer):
        vehicle = serializer.save()
        LogisticsService.refresh_vehicle_availability(vehicle)

    def perform_update(self, serializer):
        vehicle = serializer.save()
        LogisticsService.refresh_vehicle_availability(vehicle)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        vehicle = self.get_object()
        trips = DeliveryOrder.objects.filter(vehicle=vehicle, is_active=True).order_by("-scheduled_date")[:50]
        maintenance = VehicleMaintenance.objects.filter(vehicle=vehicle, is_active=True).order_by("-service_date")[:50]
        fuel = FuelRecord.objects.filter(vehicle=vehicle, is_active=True).order_by("-date")[:50]
        return api_response(
            data={
                "trips": DeliveryOrderSerializer(trips, many=True).data,
                "maintenance": MaintenanceSerializer(maintenance, many=True).data,
                "fuel": FuelRecordSerializer(fuel, many=True).data,
                "stats": LogisticsService.vehicle_stats(vehicle),
            }
        )


class DriverViewSet(LogisticsViewSetMixin, viewsets.ModelViewSet):
    queryset = Driver.objects.select_related("user").all()
    serializer_class = DriverSerializer
    filterset_class = DriverFilter
    search_fields = ["license_number", "user__first_name", "user__last_name"]
    ordering_fields = ["license_expiry", "created_at"]

    def get_create_message(self):
        return "Driver created"

    def get_update_message(self):
        return "Driver updated"

    def get_destroy_message(self):
        return "Driver deactivated"

    def perform_create(self, serializer):
        driver = serializer.save()
        from apps.hr.services import HRService

        emp = HRService.ensure_employee_for_user(
            driver.user,
            job_title="Driver",
        )
        if emp and driver.employee_number != emp.employee_number:
            driver.employee_number = emp.employee_number
            driver.save(update_fields=["employee_number", "updated_at"])
        LogisticsService.refresh_driver_availability(driver)

    def perform_update(self, serializer):
        driver = serializer.save()
        LogisticsService.refresh_driver_availability(driver)

    @action(detail=False, methods=["get"], url_path="eligible-employees")
    def eligible_employees(self, request):
        from apps.hr.services import HRService

        data = [
            {
                "id": emp.id,
                "employee_number": emp.employee_number,
                "full_name": emp.full_name,
                "department_name": emp.department.name if emp.department else "",
                "work_email": emp.work_email or "",
                "phone": emp.phone or "",
                "user_id": emp.user_id,
                "has_login": bool(emp.user_id),
            }
            for emp in HRService.eligible_driver_employees()
        ]
        return api_response(data=data)


class DeliveryOrderViewSet(LogisticsViewSetMixin, viewsets.ModelViewSet):
    queryset = DeliveryOrder.objects.select_related(
        "sales_order",
        "vehicle",
        "driver__user",
        "origin_warehouse",
        "customer",
        "created_by",
    ).prefetch_related("items__item", "items__so_item")
    serializer_class = DeliveryOrderSerializer
    filterset_class = DeliveryOrderFilter
    search_fields = ["do_number", "sales_order__so_number", "customer__name"]
    ordering_fields = ["scheduled_date", "created_at"]

    def get_create_message(self):
        return "Delivery order created"

    def get_update_message(self):
        return "Delivery order updated"

    def get_destroy_message(self):
        return "Delivery order cancelled"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in (DeliveryOrder.STATUS_SCHEDULED,):
            return api_error(message="Only scheduled orders can be cancelled.")
        LogisticsService.cancel_order(instance)
        return api_response(message="Delivery order cancelled")

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        order = self.get_object()
        if order.status != DeliveryOrder.STATUS_SCHEDULED:
            return api_error(message="Only scheduled orders can be started.")
        if not order.vehicle or not order.driver:
            return api_error(message="Assign vehicle and driver before starting trip.")
        LogisticsService.start_trip(order)
        return api_response(
            data=DeliveryOrderSerializer(order).data,
            message="Trip started",
        )

    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        order = self.get_object()
        if order.status != DeliveryOrder.STATUS_IN_TRANSIT:
            return api_error(message="Only in-transit orders can be marked delivered.")
        ser = DeliveredSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        note = LogisticsService.mark_delivered(
            order,
            signed_by=ser.validated_data["signed_by"],
            feedback=ser.validated_data.get("customer_feedback", ""),
            condition_notes=ser.validated_data.get("condition_notes", ""),
        )
        return api_response(
            data={
                "order": DeliveryOrderSerializer(order).data,
                "delivery_note": DeliveryNoteSerializer(note).data,
            },
            message="Delivery completed",
        )

    @action(detail=True, methods=["post"])
    def fail(self, request, pk=None):
        order = self.get_object()
        if order.status != DeliveryOrder.STATUS_IN_TRANSIT:
            return api_error(message="Only in-transit orders can be marked failed.")
        ser = FailedSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        LogisticsService.mark_failed(order, ser.validated_data["reason"])
        return api_response(
            data=DeliveryOrderSerializer(order).data,
            message="Delivery marked as failed",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status not in (DeliveryOrder.STATUS_SCHEDULED, DeliveryOrder.STATUS_IN_TRANSIT):
            return api_error(message="This order cannot be cancelled.")
        LogisticsService.cancel_order(order)
        return api_response(
            data=DeliveryOrderSerializer(order).data,
            message="Delivery order cancelled",
        )

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Logistics officer approves or rejects driver delivery confirmation."""
        from apps.logistics.driver_portal_serializers import LogisticsReviewSerializer
        from apps.logistics.driver_portal_service import DriverPortalService

        order = self.get_object()
        ser = LogisticsReviewSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        order = DriverPortalService.logistics_review_delivery(
            order,
            request.user,
            ser.validated_data["approved"],
            ser.validated_data.get("reason", ""),
        )
        return api_response(
            data=DeliveryOrderSerializer(order).data,
            message="Delivery approved" if ser.validated_data["approved"] else "Delivery exception recorded",
        )


class DeliveryNoteViewSet(LogisticsViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = DeliveryNote.objects.select_related(
        "delivery_order__customer"
    ).all()
    serializer_class = DeliveryNoteSerializer
    filterset_class = DeliveryNoteFilter
    search_fields = ["dn_number", "delivery_order__do_number"]
    ordering_fields = ["created_at", "signed_at"]

    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        note = self.get_object()
        if note.status != DeliveryNote.STATUS_PENDING:
            return api_error(message="Delivery note is already signed.")
        ser = SignDeliveryNoteSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        from django.utils import timezone

        note.signed_by = ser.validated_data["signed_by"]
        note.customer_feedback = ser.validated_data.get("customer_feedback", "")
        note.condition_notes = ser.validated_data.get("condition_notes", "")
        note.signed_at = timezone.now()
        note.status = DeliveryNote.STATUS_SIGNED
        note.save()
        return api_response(
            data=DeliveryNoteSerializer(note).data,
            message="Delivery note signed",
        )


class MaintenanceViewSet(LogisticsViewSetMixin, viewsets.ModelViewSet):
    queryset = VehicleMaintenance.objects.select_related("vehicle").all()
    serializer_class = MaintenanceSerializer
    filterset_class = MaintenanceFilter
    search_fields = ["vehicle__registration_number", "description", "performed_by"]
    ordering_fields = ["service_date", "cost"]

    def get_create_message(self):
        return "Maintenance scheduled"

    def get_update_message(self):
        return "Maintenance updated"

    def perform_create(self, serializer):
        record = serializer.save()
        vehicle = record.vehicle
        if record.status == VehicleMaintenance.STATUS_SCHEDULED:
            vehicle.status = Vehicle.STATUS_MAINTENANCE
            vehicle.save(update_fields=["status", "updated_at"])

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        record = self.get_object()
        if record.status == VehicleMaintenance.STATUS_COMPLETED:
            return api_error(message="Maintenance already completed.")
        ser = CompleteMaintenanceSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        LogisticsService.complete_maintenance(record, ser.validated_data)
        return api_response(
            data=MaintenanceSerializer(record).data,
            message="Maintenance completed",
        )


class FuelRecordViewSet(LogisticsViewSetMixin, viewsets.ModelViewSet):
    queryset = FuelRecord.objects.select_related(
        "vehicle", "driver__user", "recorded_by"
    ).all()
    serializer_class = FuelRecordSerializer
    filterset_class = FuelRecordFilter
    search_fields = ["vehicle__registration_number", "station_name"]
    ordering_fields = ["date", "total_cost"]

    def get_create_message(self):
        return "Fuel record created"

    def get_update_message(self):
        return "Fuel record updated"

    def get_destroy_message(self):
        return "Fuel record deleted"

    @action(detail=False, methods=["get"])
    def summary(self, request):
        data = LogisticsService.fuel_summary()
        return api_response(
            data={
                "total_cost_month": str(data["total_cost_month"]),
                "total_liters_month": str(data["total_liters_month"]),
                "avg_cost_per_km": str(data["avg_cost_per_km"]),
            }
        )


class LogisticsDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        data = LogisticsService.dashboard_data()
        live_ids = data.pop("live_delivery_ids", [])
        live_qs = DeliveryOrder.objects.filter(id__in=live_ids).select_related(
            "customer", "driver__user", "vehicle"
        )
        data["live_deliveries"] = DeliveryOrderSerializer(live_qs, many=True).data
        return api_response(data=data)


class SalesOrderLogisticsViewSet(LogisticsViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Logistics-facing sales order queue and delivery workflow actions."""

    serializer_class = SalesOrderLogisticsSerializer
    search_fields = ["so_number", "customer__name"]
    ordering_fields = ["created_at", "updated_at", "so_number"]

    QUEUE_STATUSES = {
        "delivery_cost": {SalesOrder.STATUS_DELIVERY_COST_CALC},
        "dispatch": {
            SalesOrder.STATUS_PAYMENT_CONFIRMED,
            SalesOrder.STATUS_READY_FOR_PICKUP,
            SalesOrder.STATUS_READY_FOR_DELIVERY,
            SalesOrder.STATUS_VEHICLE_ASSIGNED,
            SalesOrder.STATUS_THIRD_PARTY_ASSIGNED,
        },
        "in_transit": {
            SalesOrder.STATUS_DISPATCHED,
            SalesOrder.STATUS_IN_TRANSIT,
            SalesOrder.STATUS_DELIVERED,
        },
    }

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SalesOrderLogisticsDetailSerializer
        return SalesOrderLogisticsSerializer

    def get_queryset(self):
        qs = (
            SalesOrder.objects.filter(is_active=True)
            .select_related(
                "customer",
                "currency",
                "created_by",
                "fulfillment_warehouse",
                "delivery_cost_detail",
                "dispatch_assignment",
                "dispatch_assignment__vehicle",
                "dispatch_assignment__driver__user",
            )
            .prefetch_related(
                "items__item",
                "delivery_orders__vehicle",
                "delivery_orders__driver__user",
                "delivery_orders__origin_warehouse",
            )
        )
        queue = self.request.query_params.get("queue")
        if queue and queue in self.QUEUE_STATUSES:
            qs = qs.filter(status__in=self.QUEUE_STATUSES[queue])
        else:
            all_statuses = set()
            for statuses in self.QUEUE_STATUSES.values():
                all_statuses.update(statuses)
            qs = qs.filter(status__in=all_statuses)
        return qs.order_by("-updated_at")

    def retrieve(self, request, *args, **kwargs):
        from apps.sales.workflow import SalesOrderWorkflow

        order = self.get_object()
        SalesOrderWorkflow.ensure_fleet_matches_order(order)
        order.refresh_from_db()
        response = super().retrieve(request, *args, **kwargs)
        return response

    @action(detail=True, methods=["post"])
    def delivery_cost(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.workflow_serializers import DeliveryCostSerializer
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        ser = DeliveryCostSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.calculate_delivery_cost(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data=SalesOrderSerializer(order).data,
            message="Delivery cost calculated",
        )

    @action(detail=True, methods=["post"])
    def set_delivery_method(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.workflow_serializers import DeliveryMethodSerializer
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        ser = DeliveryMethodSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.set_delivery_method(
                order, request.user, ser.validated_data["delivery_method"]
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Delivery method set")

    @action(detail=True, methods=["post"])
    def assign_vehicle(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.workflow_serializers import VehicleAssignmentSerializer
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        ser = VehicleAssignmentSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.assign_vehicle(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Vehicle assigned")

    @action(detail=True, methods=["post"])
    def assign_third_party(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.workflow_serializers import ThirdPartyAssignmentSerializer
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        ser = ThirdPartyAssignmentSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.assign_third_party(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Third party assigned")

    @action(detail=True, methods=["post"], url_path="dispatch-order")
    def dispatch_order(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        try:
            SalesOrderWorkflow.dispatch_order(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Order dispatched")

    @action(detail=True, methods=["post"])
    def confirm_pickup(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.workflow_serializers import PickupConfirmSerializer
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        ser = PickupConfirmSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.confirm_pickup(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Pickup completed")

    @action(detail=True, methods=["post"])
    def confirm_delivery(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.workflow_serializers import DeliveryConfirmSerializer
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        ser = DeliveryConfirmSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.confirm_delivery(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Delivery confirmed")

    @action(detail=True, methods=["post"])
    def logistics_confirm(self, request, pk=None):
        from apps.sales.workflow import SalesOrderWorkflow
        from apps.sales.serializers import SalesOrderSerializer

        order = self.get_object()
        try:
            SalesOrderWorkflow.logistics_confirm(
                order, request.user, request.data.get("remarks", "")
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Logistics confirmed")
