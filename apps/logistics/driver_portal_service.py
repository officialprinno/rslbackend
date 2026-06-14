"""Driver portal workflow — trip lifecycle, confirmations, fleet status."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.logistics.models import (
    DeliveryConfirmation,
    DeliveryOrder,
    DeliveryTripEvent,
    Driver,
    Vehicle,
    VehicleConditionReport,
    VehicleMaintenance,
)
from apps.logistics.services import LogisticsService
from apps.messaging.models import AppNotification
from apps.sales.models import SalesOrder


class DriverPortalService:
    """Enterprise driver trip workflow integrated with logistics and sales."""

    ACTIVE_TRIP_STATUSES = (
        DeliveryOrder.TRIP_ASSIGNED,
        DeliveryOrder.TRIP_STARTED,
        DeliveryOrder.TRIP_IN_TRANSIT,
        DeliveryOrder.TRIP_ARRIVED,
        DeliveryOrder.TRIP_DELIVERED,
        DeliveryOrder.TRIP_RETURNING,
    )

    @staticmethod
    def get_driver_for_user(user) -> Driver:
        profile = getattr(user, "driver_profile", None)
        if not profile or not profile.is_active:
            raise ValidationError("No active driver profile linked to this account.")
        return profile

    @staticmethod
    def _log_event(
        order: DeliveryOrder,
        user,
        action: str,
        from_status: str = "",
        to_status: str = "",
        details: str = "",
    ) -> None:
        DeliveryTripEvent.objects.create(
            delivery_order=order,
            action=action,
            from_status=from_status,
            to_status=to_status,
            details=details,
            user=user,
        )

    @staticmethod
    def _notify_user(user, title: str, message: str, link: str = "") -> None:
        if not user:
            return
        AppNotification.objects.create(
            user=user,
            title=title,
            body=message[:250],
            navigate_to=link or None,
            notification_type=AppNotification.TYPE_ALERT,
            icon="truck",
            color="blue",
        )

    @staticmethod
    def _notify_logistics(title: str, message: str, link: str = "") -> None:
        from apps.users.models import Permission, User

        role_ids = Permission.objects.filter(
            module="logistics",
            action__in=("create", "update"),
            is_active=True,
        ).values_list("role_id", flat=True)
        users = User.objects.filter(role_id__in=role_ids, is_active=True).distinct()
        for user in users[:50]:
            DriverPortalService._notify_user(user, title, message, link)

    @staticmethod
    def _set_driver_status(driver: Driver, status: str, available: bool | None = None) -> None:
        driver.availability_status = status
        update = ["availability_status", "updated_at"]
        if available is not None:
            driver.is_available = available
            update.append("is_available")
        driver.save(update_fields=update)

    @staticmethod
    def _set_vehicle_status(vehicle: Vehicle | None, status: str) -> None:
        if not vehicle:
            return
        vehicle.status = status
        vehicle.save(update_fields=["status", "updated_at"])

    @staticmethod
    def ensure_assigned(order: DeliveryOrder) -> None:
        """Mark trip as assigned when logistics sets driver/vehicle."""
        if order.trip_status == DeliveryOrder.TRIP_ASSIGNED:
            return
        if order.driver_id and order.status == DeliveryOrder.STATUS_SCHEDULED:
            order.trip_status = DeliveryOrder.TRIP_ASSIGNED
            order.save(update_fields=["trip_status", "updated_at"])
            driver = order.driver
            if order.vehicle_id and driver.assigned_vehicle_id != order.vehicle_id:
                driver.assigned_vehicle = order.vehicle
                driver.save(update_fields=["assigned_vehicle", "updated_at"])
            if driver.user_id:
                DriverPortalService._notify_user(
                    driver.user,
                    f"New delivery assignment — {order.do_number}",
                    f"Order {order.sales_order.so_number} to {order.destination[:80]}",
                    f"/driver-portal/trips/{order.id}",
                )

    @staticmethod
    def driver_dashboard(driver: Driver) -> dict:
        orders = DeliveryOrder.objects.filter(driver=driver, is_active=True)
        active = orders.filter(trip_status__in=DriverPortalService.ACTIVE_TRIP_STATUSES).exclude(
            trip_status=DeliveryOrder.TRIP_RETURN_CONFIRMED
        )
        vehicle = driver.assigned_vehicle
        if not vehicle and active.exists():
            vehicle = active.first().vehicle
        return {
            "assigned_count": orders.filter(trip_status=DeliveryOrder.TRIP_ASSIGNED).count(),
            "in_progress_count": active.exclude(trip_status=DeliveryOrder.TRIP_ASSIGNED).count(),
            "completed_count": orders.filter(
                trip_status=DeliveryOrder.TRIP_RETURN_CONFIRMED
            ).count(),
            "current_vehicle": vehicle,
            "availability_status": driver.availability_status,
            "active_trip_id": active.exclude(trip_status=DeliveryOrder.TRIP_ASSIGNED)
            .values_list("id", flat=True)
            .first(),
        }

    @staticmethod
    @transaction.atomic
    def start_delivery(
        order: DeliveryOrder,
        driver: Driver,
        user,
        odometer_start: int,
        vehicle_condition: str = "GOOD",
    ) -> DeliveryOrder:
        if order.driver_id != driver.id:
            raise ValidationError("This delivery is not assigned to you.")
        if order.trip_status not in (
            DeliveryOrder.TRIP_ASSIGNED,
        ):
            raise ValidationError("Delivery cannot be started in current status.")
        vehicle, _ = LogisticsService.resolve_delivery_fleet(order)
        if not vehicle:
            raise ValidationError("No vehicle assigned to this delivery.")

        now = timezone.now()
        prev = order.trip_status
        order.trip_status = DeliveryOrder.TRIP_STARTED
        order.status = DeliveryOrder.STATUS_IN_TRANSIT
        order.trip_started_at = now
        order.actual_departure = now
        order.odometer_start = odometer_start
        order.vehicle_condition_start = vehicle_condition
        order.vehicle = vehicle
        order.driver = driver
        order.save(
            update_fields=[
                "trip_status",
                "status",
                "trip_started_at",
                "actual_departure",
                "odometer_start",
                "vehicle_condition_start",
                "vehicle",
                "driver",
                "updated_at",
            ]
        )

        DriverPortalService._set_driver_status(driver, Driver.AVAIL_ON_DELIVERY, available=False)
        DriverPortalService._set_vehicle_status(vehicle, Vehicle.STATUS_IN_USE)
        if vehicle.odometer_reading < odometer_start:
            vehicle.odometer_reading = odometer_start
            vehicle.save(update_fields=["odometer_reading", "updated_at"])

        so = order.sales_order
        if so.status in (SalesOrder.STATUS_VEHICLE_ASSIGNED, SalesOrder.STATUS_READY_FOR_DELIVERY):
            so.status = SalesOrder.STATUS_IN_TRANSIT
            so.save(update_fields=["status", "updated_at"])

        DriverPortalService._log_event(
            order, user, "Trip Started", prev, order.trip_status,
            f"Odometer: {odometer_start}, Condition: {vehicle_condition}",
        )
        order.trip_status = DeliveryOrder.TRIP_IN_TRANSIT
        order.save(update_fields=["trip_status", "updated_at"])
        DriverPortalService._log_event(
            order, user, "In Transit", DeliveryOrder.TRIP_STARTED, order.trip_status
        )
        LogisticsService.set_fleet_in_transit(vehicle, driver)
        return order

    @staticmethod
    @transaction.atomic
    def confirm_arrival(order: DeliveryOrder, driver: Driver, user, notes: str = "") -> DeliveryOrder:
        if order.driver_id != driver.id:
            raise ValidationError("This delivery is not assigned to you.")
        if order.trip_status != DeliveryOrder.TRIP_IN_TRANSIT:
            raise ValidationError("Trip must be in transit before confirming arrival.")

        now = timezone.now()
        prev = order.trip_status
        order.trip_status = DeliveryOrder.TRIP_ARRIVED
        order.arrived_at = now
        if notes:
            order.notes = (order.notes + "\n" + notes).strip() if order.notes else notes
        order.save(update_fields=["trip_status", "arrived_at", "notes", "updated_at"])
        DriverPortalService._log_event(
            order, user, "Arrived at Destination", prev, order.trip_status, notes
        )
        return order

    @staticmethod
    @transaction.atomic
    def confirm_delivery(
        order: DeliveryOrder,
        driver: Driver,
        user,
        data: dict,
    ) -> DeliveryOrder:
        if order.driver_id != driver.id:
            raise ValidationError("This delivery is not assigned to you.")
        if order.trip_status != DeliveryOrder.TRIP_ARRIVED:
            raise ValidationError("Confirm arrival before completing delivery.")

        now = timezone.now()
        prev = order.trip_status
        order.trip_status = DeliveryOrder.TRIP_DELIVERED
        order.delivered_at = now
        order.actual_arrival = now
        order.status = DeliveryOrder.STATUS_DELIVERED
        order.logistics_review_status = DeliveryOrder.REVIEW_PENDING
        order.save(
            update_fields=[
                "trip_status",
                "delivered_at",
                "actual_arrival",
                "status",
                "logistics_review_status",
                "updated_at",
            ]
        )

        DeliveryConfirmation.objects.update_or_create(
            delivery_order=order,
            defaults={
                "receiver_name": data["receiver_name"],
                "receiver_position": data.get("receiver_position", ""),
                "receiver_phone": data.get("receiver_phone", ""),
                "receiver_company": data.get("receiver_company", ""),
                "quantity_delivered": Decimal(str(data.get("quantity_delivered", 0))),
                "delivery_notes": data.get("delivery_notes", ""),
                "signature_data": data.get("signature_data", ""),
                "proof_photo_url": data.get("proof_photo_url", ""),
                "proof_document_url": data.get("proof_document_url", ""),
                "confirmed_by": user,
                "confirmed_at": now,
            },
        )

        for line in order.items.select_related("so_item"):
            qty = min(
                line.quantity,
                line.so_item.quantity_ordered - line.so_item.quantity_delivered,
            )
            if qty > 0:
                line.so_item.quantity_delivered += qty
                line.so_item.save(update_fields=["quantity_delivered"])

        so = order.sales_order
        all_delivered = all(
            item.quantity_delivered >= item.quantity_ordered for item in so.items.all()
        )
        if all_delivered:
            so.delivery_status = SalesOrder.DELIVERY_DELIVERED
            so.status = SalesOrder.STATUS_DELIVERED
        else:
            so.delivery_status = SalesOrder.DELIVERY_PARTIAL
        so.save(update_fields=["delivery_status", "status", "updated_at"])

        DriverPortalService._log_event(
            order, user, "Delivery Confirmed", prev, order.trip_status,
            f"Receiver: {data['receiver_name']}",
        )
        DriverPortalService._notify_logistics(
            f"Delivery confirmed — {order.do_number}",
            f"Driver {driver.user.get_full_name()} confirmed delivery. Review and approve.",
            f"/logistics/deliveries/{order.id}/view",
        )
        return order

    @staticmethod
    @transaction.atomic
    def start_return(
        order: DeliveryOrder,
        driver: Driver,
        user,
        vehicle_condition: str = "GOOD",
    ) -> DeliveryOrder:
        if order.driver_id != driver.id:
            raise ValidationError("This delivery is not assigned to you.")
        if order.trip_status != DeliveryOrder.TRIP_DELIVERED:
            raise ValidationError("Complete delivery before starting return.")

        now = timezone.now()
        prev = order.trip_status
        order.trip_status = DeliveryOrder.TRIP_RETURNING
        order.return_started_at = now
        if vehicle_condition:
            order.vehicle_condition_end = vehicle_condition
        order.save(
            update_fields=[
                "trip_status",
                "return_started_at",
                "vehicle_condition_end",
                "updated_at",
            ]
        )
        DriverPortalService._set_driver_status(driver, Driver.AVAIL_RETURNING, available=False)
        vehicle, _ = LogisticsService.resolve_delivery_fleet(order)
        DriverPortalService._set_vehicle_status(vehicle, Vehicle.STATUS_RETURNING)
        DriverPortalService._log_event(
            order, user, "Return Started", prev, order.trip_status, vehicle_condition
        )
        return order

    @staticmethod
    @transaction.atomic
    def confirm_return(
        order: DeliveryOrder,
        driver: Driver,
        user,
        odometer_end: int,
        fuel_remaining: Decimal | None = None,
        vehicle_condition: str = "GOOD",
    ) -> DeliveryOrder:
        if order.driver_id != driver.id:
            raise ValidationError("This delivery is not assigned to you.")
        if order.trip_status != DeliveryOrder.TRIP_RETURNING:
            raise ValidationError("Start return trip before confirming return.")

        now = timezone.now()
        prev = order.trip_status
        order.trip_status = DeliveryOrder.TRIP_RETURN_CONFIRMED
        order.return_confirmed_at = now
        order.odometer_end = odometer_end
        order.vehicle_condition_end = vehicle_condition
        if fuel_remaining is not None:
            order.fuel_remaining = fuel_remaining
        order.save(
            update_fields=[
                "trip_status",
                "return_confirmed_at",
                "odometer_end",
                "vehicle_condition_end",
                "fuel_remaining",
                "updated_at",
            ]
        )

        vehicle, _ = LogisticsService.resolve_delivery_fleet(order)
        if vehicle:
            if vehicle.odometer_reading < odometer_end:
                vehicle.odometer_reading = odometer_end
            vehicle.status = Vehicle.STATUS_AVAILABLE
            vehicle.save(update_fields=["odometer_reading", "status", "updated_at"])

        DriverPortalService._set_driver_status(driver, Driver.AVAIL_AVAILABLE, available=True)
        LogisticsService.release_fleet(vehicle, driver)

        DriverPortalService._log_event(
            order, user, "Return Confirmed", prev, order.trip_status,
            f"Odometer end: {odometer_end}",
        )
        DriverPortalService._notify_logistics(
            f"Driver returned — {order.do_number}",
            f"{driver.user.get_full_name()} completed return trip.",
            f"/logistics/deliveries/{order.id}/view",
        )
        return order

    @staticmethod
    @transaction.atomic
    def report_vehicle_condition(
        driver: Driver,
        user,
        data: dict,
    ) -> VehicleConditionReport:
        vehicle_id = data.get("vehicle")
        vehicle = Vehicle.objects.filter(pk=vehicle_id, is_active=True).first()
        if not vehicle:
            raise ValidationError("Vehicle not found.")
        order = None
        if data.get("delivery_order"):
            order = DeliveryOrder.objects.filter(
                pk=data["delivery_order"], driver=driver, is_active=True
            ).first()

        report = VehicleConditionReport.objects.create(
            vehicle=vehicle,
            driver=driver,
            delivery_order=order,
            condition=data["condition"],
            notes=data.get("notes", ""),
            odometer_reading=data.get("odometer_reading"),
            fuel_remaining=data.get("fuel_remaining"),
            photo_url=data.get("photo_url", ""),
        )

        if data["condition"] == VehicleConditionReport.COND_BREAKDOWN:
            vehicle.status = Vehicle.STATUS_OUT_OF_SERVICE
            vehicle.save(update_fields=["status", "updated_at"])
            VehicleMaintenance.objects.create(
                vehicle=vehicle,
                maintenance_type=VehicleMaintenance.TYPE_REPAIR,
                description=f"Breakdown reported by driver: {data.get('notes', '')[:500]}",
                service_date=timezone.now().date(),
                status=VehicleMaintenance.STATUS_SCHEDULED,
            )
            DriverPortalService._notify_logistics(
                f"Vehicle breakdown — {vehicle.registration_number}",
                data.get("notes", "Driver reported breakdown."),
                f"/logistics/vehicles/{vehicle.id}",
            )
        elif data["condition"] == VehicleConditionReport.COND_MAINTENANCE:
            vehicle.status = Vehicle.STATUS_MAINTENANCE
            vehicle.save(update_fields=["status", "updated_at"])
            VehicleMaintenance.objects.create(
                vehicle=vehicle,
                maintenance_type=VehicleMaintenance.TYPE_INSPECTION,
                description=f"Maintenance required: {data.get('notes', '')[:500]}",
                service_date=timezone.now().date(),
                status=VehicleMaintenance.STATUS_SCHEDULED,
            )
            DriverPortalService._notify_logistics(
                f"Maintenance required — {vehicle.registration_number}",
                data.get("notes", "Driver reported maintenance need."),
                "/logistics/maintenance",
            )

        if order:
            DriverPortalService._log_event(
                order, user, "Vehicle Condition Report", "", "",
                f"{data['condition']}: {data.get('notes', '')}",
            )
        return report

    @staticmethod
    @transaction.atomic
    def logistics_review_delivery(
        order: DeliveryOrder,
        user,
        approved: bool,
        reason: str = "",
    ) -> DeliveryOrder:
        if order.trip_status != DeliveryOrder.TRIP_DELIVERED:
            raise ValidationError("Delivery must be confirmed by driver first.")
        if order.logistics_review_status != DeliveryOrder.REVIEW_PENDING:
            raise ValidationError("Delivery already reviewed.")

        if approved:
            order.logistics_review_status = DeliveryOrder.REVIEW_APPROVED
            so = order.sales_order
            if so.status == SalesOrder.STATUS_DELIVERED:
                so.status = SalesOrder.STATUS_DELIVERY_CONFIRMED
                so.save(update_fields=["status", "updated_at"])
            if order.driver and order.driver.user_id:
                DriverPortalService._notify_user(
                    order.driver.user,
                    f"Delivery approved — {order.do_number}",
                    "Logistics confirmed your delivery submission.",
                )
        else:
            order.logistics_review_status = DeliveryOrder.REVIEW_REJECTED
            order.notes = (order.notes + f"\nReview rejected: {reason}").strip()
            if order.driver and order.driver.user_id:
                DriverPortalService._notify_user(
                    order.driver.user,
                    f"Delivery exception — {order.do_number}",
                    reason or "Logistics flagged an issue with this delivery.",
                    f"/driver-portal/trips/{order.id}",
                )
        order.save(update_fields=["logistics_review_status", "notes", "updated_at"])
        DriverPortalService._log_event(
            order, user,
            "Logistics Approved" if approved else "Logistics Rejected",
            DeliveryOrder.REVIEW_PENDING,
            order.logistics_review_status,
            reason,
        )
        return order

    @staticmethod
    def driver_performance(driver: Driver) -> dict:
        stats = LogisticsService.driver_stats(driver)
        completed = DeliveryOrder.objects.filter(
            driver=driver,
            trip_status=DeliveryOrder.TRIP_RETURN_CONFIRMED,
            is_active=True,
        )
        durations = []
        for trip in completed.filter(
            trip_started_at__isnull=False, return_confirmed_at__isnull=False
        )[:100]:
            delta = trip.return_confirmed_at - trip.trip_started_at
            durations.append(delta.total_seconds() / 3600)
        avg_hours = round(sum(durations) / len(durations), 1) if durations else 0
        return {
            **stats,
            "completed_returns": completed.count(),
            "avg_trip_hours": avg_hours,
        }
