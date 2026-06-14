"""Logistics business logic."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Sum
from django.utils import timezone

from apps.logistics.models import (
    DeliveryNote,
    DeliveryOrder,
    Driver,
    FuelRecord,
    Vehicle,
    VehicleMaintenance,
)
from apps.logistics.utils import generate_document_number
from apps.sales.models import SalesOrder


class LogisticsService:
    """Fleet operations, compliance, and delivery workflow."""

    @staticmethod
    def days_until(date_value) -> int | None:
        if not date_value:
            return None
        return (date_value - timezone.now().date()).days

    @staticmethod
    def compliance_severity(days_remaining: int | None) -> str | None:
        if days_remaining is None:
            return None
        if days_remaining < 0:
            return "EXPIRED"
        if days_remaining <= 30:
            return "EXPIRING_SOON"
        return None

    @staticmethod
    def service_severity(days_remaining: int | None) -> str | None:
        if days_remaining is None:
            return None
        if days_remaining < 0:
            return "EXPIRED"
        if days_remaining <= 7:
            return "EXPIRING_SOON"
        return None

    @staticmethod
    def refresh_vehicle_availability(vehicle: Vehicle) -> None:
        today = timezone.now().date()
        unavailable = False
        if vehicle.insurance_expiry and vehicle.insurance_expiry < today:
            unavailable = True
        if vehicle.road_licence_expiry and vehicle.road_licence_expiry < today:
            unavailable = True
        if vehicle.next_service_date and vehicle.next_service_date < today:
            unavailable = True
        if unavailable and vehicle.status == Vehicle.STATUS_AVAILABLE:
            vehicle.status = Vehicle.STATUS_MAINTENANCE
            vehicle.save(update_fields=["status", "updated_at"])

    @staticmethod
    def refresh_driver_availability(driver: Driver) -> None:
        today = timezone.now().date()
        if driver.license_expiry < today or driver.medical_expiry < today:
            if driver.is_available:
                driver.is_available = False
                driver.save(update_fields=["is_available", "updated_at"])

    @staticmethod
    def vehicle_stats(vehicle: Vehicle) -> dict:
        month_start = timezone.now().date().replace(day=1)
        orders = DeliveryOrder.objects.filter(vehicle=vehicle, is_active=True)
        delivered = orders.filter(status=DeliveryOrder.STATUS_DELIVERED)
        fuel = FuelRecord.objects.filter(
            vehicle=vehicle,
            is_active=True,
            date__gte=month_start,
        ).aggregate(total=Sum("total_cost"))["total"] or Decimal("0")
        return {
            "total_trips": delivered.count(),
            "total_km": delivered.aggregate(total=Sum("distance_km"))["total"] or Decimal("0"),
            "fuel_this_month": fuel,
        }

    @staticmethod
    def driver_stats(driver: Driver) -> dict:
        month_start = timezone.now().date().replace(day=1)
        trips = DeliveryOrder.objects.filter(
            driver=driver,
            is_active=True,
            status=DeliveryOrder.STATUS_DELIVERED,
            actual_arrival__date__gte=month_start,
        )
        total = trips.count()
        on_time = trips.filter(actual_arrival__lte=F("scheduled_date")).count() if total else 0
        return {
            "total_trips": total,
            "on_time_percent": round(on_time / total * 100, 1) if total else 100.0,
            "incidents_count": driver.incidents_count,
        }

    @staticmethod
    def set_fleet_in_transit(vehicle: Vehicle | None = None, driver: Driver | None = None) -> None:
        """Mark assigned vehicle and driver as in transit."""
        if vehicle:
            vehicle.refresh_from_db(fields=["status"])
            if vehicle.status in (Vehicle.STATUS_AVAILABLE, Vehicle.STATUS_ON_TRIP, Vehicle.STATUS_IN_USE):
                vehicle.status = Vehicle.STATUS_ON_TRIP
                vehicle.save(update_fields=["status", "updated_at"])
        if driver:
            driver.refresh_from_db(fields=["is_available"])
            if driver.is_available:
                driver.is_available = False
                driver.save(update_fields=["is_available", "updated_at"])

    @staticmethod
    def _vehicle_has_active_trip(vehicle: Vehicle) -> bool:
        from apps.sales.models import SalesOrder

        if DeliveryOrder.objects.filter(
            vehicle=vehicle,
            status=DeliveryOrder.STATUS_IN_TRANSIT,
            is_active=True,
        ).exists():
            return True
        if DeliveryOrder.objects.filter(
            vehicle=vehicle,
            trip_status__in=(
                DeliveryOrder.TRIP_STARTED,
                DeliveryOrder.TRIP_IN_TRANSIT,
                DeliveryOrder.TRIP_ARRIVED,
                DeliveryOrder.TRIP_DELIVERED,
                DeliveryOrder.TRIP_RETURNING,
            ),
            is_active=True,
        ).exists():
            return True
        return SalesOrder.objects.filter(
            is_active=True,
            status__in=(SalesOrder.STATUS_DISPATCHED, SalesOrder.STATUS_IN_TRANSIT),
            dispatch_assignment__vehicle=vehicle,
        ).exists()

    @staticmethod
    def _driver_has_active_trip(driver: Driver) -> bool:
        from apps.sales.models import SalesOrder

        if DeliveryOrder.objects.filter(
            driver=driver,
            status=DeliveryOrder.STATUS_IN_TRANSIT,
            is_active=True,
        ).exists():
            return True
        if DeliveryOrder.objects.filter(
            driver=driver,
            trip_status__in=(
                DeliveryOrder.TRIP_STARTED,
                DeliveryOrder.TRIP_IN_TRANSIT,
                DeliveryOrder.TRIP_ARRIVED,
                DeliveryOrder.TRIP_DELIVERED,
                DeliveryOrder.TRIP_RETURNING,
            ),
            is_active=True,
        ).exists():
            return True
        return SalesOrder.objects.filter(
            is_active=True,
            status__in=(SalesOrder.STATUS_DISPATCHED, SalesOrder.STATUS_IN_TRANSIT),
            dispatch_assignment__driver=driver,
        ).exists()

    @staticmethod
    def release_fleet(vehicle: Vehicle | None = None, driver: Driver | None = None) -> None:
        """Return vehicle and driver to available pool after trip ends."""
        if vehicle:
            vehicle.refresh_from_db(fields=["status"])
            if (
                vehicle.status in (Vehicle.STATUS_ON_TRIP, Vehicle.STATUS_IN_USE, Vehicle.STATUS_RETURNING)
                and not LogisticsService._vehicle_has_active_trip(vehicle)
            ):
                vehicle.status = Vehicle.STATUS_AVAILABLE
                vehicle.save(update_fields=["status", "updated_at"])
        if driver:
            driver.refresh_from_db(fields=["is_available"])
            if (
                not driver.is_available
                and not LogisticsService._driver_has_active_trip(driver)
            ):
                driver.is_available = True
                driver.save(update_fields=["is_available", "updated_at"])

    @staticmethod
    def resolve_delivery_fleet(delivery: DeliveryOrder) -> tuple[Vehicle | None, Driver | None]:
        """Return vehicle/driver from the delivery order or linked sales assignment."""
        vehicle = delivery.vehicle if delivery.vehicle_id else None
        driver = delivery.driver if delivery.driver_id else None
        if vehicle and driver:
            return vehicle, driver
        assignment = getattr(delivery.sales_order, "dispatch_assignment", None)
        if assignment:
            vehicle = vehicle or (assignment.vehicle if assignment.vehicle_id else None)
            driver = driver or (assignment.driver if assignment.driver_id else None)
        return vehicle, driver

    @staticmethod
    def start_trip(order: DeliveryOrder) -> None:
        now = timezone.now()
        vehicle, driver = LogisticsService.resolve_delivery_fleet(order)
        if vehicle and not order.vehicle_id:
            order.vehicle = vehicle
        if driver and not order.driver_id:
            order.driver = driver
        order.status = DeliveryOrder.STATUS_IN_TRANSIT
        order.actual_departure = now
        order.save(
            update_fields=[
                "status",
                "actual_departure",
                "vehicle",
                "driver",
                "updated_at",
            ]
        )
        LogisticsService.set_fleet_in_transit(vehicle, driver)

    @staticmethod
    def mark_delivered(order: DeliveryOrder, signed_by: str, feedback: str = "", condition_notes: str = "") -> DeliveryNote:
        now = timezone.now()
        order.status = DeliveryOrder.STATUS_DELIVERED
        order.actual_arrival = now
        order.save(update_fields=["status", "actual_arrival", "updated_at"])

        for line in order.items.select_related("so_item"):
            so_item = line.so_item
            so_item.quantity_delivered += line.quantity
            so_item.save(update_fields=["quantity_delivered"])

        so = order.sales_order
        all_delivered = all(
            item.quantity_delivered >= item.quantity_ordered for item in so.items.all()
        )
        any_delivered = any(item.quantity_delivered > 0 for item in so.items.all())
        if all_delivered:
            so.delivery_status = SalesOrder.DELIVERY_DELIVERED
            so.status = SalesOrder.STATUS_DELIVERED
        elif any_delivered:
            so.delivery_status = SalesOrder.DELIVERY_PARTIAL
            so.status = SalesOrder.STATUS_PARTIAL
        so.save(update_fields=["delivery_status", "status", "updated_at"])

        vehicle, driver = LogisticsService.resolve_delivery_fleet(order)
        LogisticsService.release_fleet(vehicle, driver)

        note, _ = DeliveryNote.objects.get_or_create(
            delivery_order=order,
            defaults={
                "dn_number": generate_document_number("DN", DeliveryNote, "dn_number"),
                "signed_by": signed_by,
                "signed_at": now,
                "customer_feedback": feedback,
                "condition_notes": condition_notes,
                "status": DeliveryNote.STATUS_SIGNED,
            },
        )
        if note.status == DeliveryNote.STATUS_PENDING:
            note.signed_by = signed_by
            note.signed_at = now
            note.customer_feedback = feedback
            note.condition_notes = condition_notes
            note.status = DeliveryNote.STATUS_SIGNED
            note.save()
        return note

    @staticmethod
    def mark_failed(order: DeliveryOrder, reason: str) -> None:
        order.status = DeliveryOrder.STATUS_FAILED
        order.failure_reason = reason
        order.save(update_fields=["status", "failure_reason", "updated_at"])
        vehicle, driver = LogisticsService.resolve_delivery_fleet(order)
        LogisticsService.release_fleet(vehicle, driver)

    @staticmethod
    def cancel_order(order: DeliveryOrder) -> None:
        order.status = DeliveryOrder.STATUS_CANCELLED
        order.save(update_fields=["status", "updated_at"])
        vehicle, driver = LogisticsService.resolve_delivery_fleet(order)
        LogisticsService.release_fleet(vehicle, driver)

    @staticmethod
    def complete_maintenance(record: VehicleMaintenance, data: dict) -> None:
        for field, value in data.items():
            setattr(record, field, value)
        record.status = VehicleMaintenance.STATUS_COMPLETED
        record.save()
        vehicle = record.vehicle
        vehicle.last_service_date = record.service_date
        if record.next_service_date:
            vehicle.next_service_date = record.next_service_date
        if record.odometer_reading:
            vehicle.odometer_reading = record.odometer_reading
        if vehicle.status == Vehicle.STATUS_MAINTENANCE:
            vehicle.status = Vehicle.STATUS_AVAILABLE
        vehicle.save(
            update_fields=[
                "last_service_date",
                "next_service_date",
                "odometer_reading",
                "status",
                "updated_at",
            ]
        )

    @staticmethod
    def fuel_summary() -> dict:
        month_start = timezone.now().date().replace(day=1)
        records = FuelRecord.objects.filter(is_active=True, date__gte=month_start)
        total_cost = records.aggregate(total=Sum("total_cost"))["total"] or Decimal("0")
        total_liters = records.aggregate(total=Sum("liters"))["total"] or Decimal("0")
        km_agg = records.aggregate(max_odo=Sum("odometer_reading"))
        avg_cost_per_km = Decimal("0")
        if records.exists():
            total_km = sum(
                (r.odometer_reading for r in records if r.odometer_reading),
                0,
            )
            if total_km > 0:
                avg_cost_per_km = (total_cost / Decimal(total_km)).quantize(Decimal("0.01"))
        return {
            "total_cost_month": total_cost,
            "total_liters_month": total_liters,
            "avg_cost_per_km": avg_cost_per_km,
        }

    @staticmethod
    def compliance_alerts() -> list:
        today = timezone.now().date()
        alerts = []

        for v in Vehicle.objects.filter(is_active=True):
            for field, alert_type in (
                ("insurance_expiry", "INSURANCE"),
                ("road_licence_expiry", "LICENCE"),
            ):
                expiry = getattr(v, field)
                if not expiry:
                    continue
                days = (expiry - today).days
                severity = LogisticsService.compliance_severity(days)
                if severity:
                    alerts.append(
                        {
                            "type": alert_type,
                            "severity": severity,
                            "vehicle_id": v.id,
                            "name": v.registration_number,
                            "expiry_date": expiry.isoformat(),
                            "days_remaining": days,
                        }
                    )
            if v.next_service_date:
                days = (v.next_service_date - today).days
                severity = LogisticsService.service_severity(days)
                if severity:
                    alerts.append(
                        {
                            "type": "SERVICE",
                            "severity": severity,
                            "vehicle_id": v.id,
                            "name": v.registration_number,
                            "expiry_date": v.next_service_date.isoformat(),
                            "days_remaining": days,
                        }
                    )

        for d in Driver.objects.filter(is_active=True).select_related("user"):
            for field, alert_type in (
                ("license_expiry", "DRIVER_LICENCE"),
                ("medical_expiry", "MEDICAL"),
            ):
                expiry = getattr(d, field)
                days = (expiry - today).days
                severity = LogisticsService.compliance_severity(days)
                if severity:
                    alerts.append(
                        {
                            "type": alert_type,
                            "severity": severity,
                            "driver_id": d.id,
                            "name": d.user.get_full_name(),
                            "expiry_date": expiry.isoformat(),
                            "days_remaining": days,
                        }
                    )
        return alerts

    @staticmethod
    def dashboard_data() -> dict:
        today = timezone.now().date()
        orders = DeliveryOrder.objects.filter(is_active=True)
        live = orders.filter(status=DeliveryOrder.STATUS_IN_TRANSIT)
        month_start = today.replace(day=1)
        weekly = []
        for week in range(4):
            start = month_start + timedelta(days=week * 7)
            end = start + timedelta(days=6)
            count = orders.filter(
                scheduled_date__date__gte=start,
                scheduled_date__date__lte=end,
                status=DeliveryOrder.STATUS_DELIVERED,
            ).count()
            weekly.append({"week": start.isoformat(), "count": count})

        fuel_weekly = []
        for week in range(4):
            start = month_start + timedelta(days=week * 7)
            end = start + timedelta(days=6)
            total = FuelRecord.objects.filter(
                is_active=True,
                date__gte=start,
                date__lte=end,
            ).aggregate(total=Sum("total_cost"))["total"] or Decimal("0")
            fuel_weekly.append({"week": start.isoformat(), "total": str(total)})

        return {
            "active_deliveries": live.count(),
            "deliveries_today": orders.filter(scheduled_date__date=today).count(),
            "vehicles_available": Vehicle.objects.filter(
                is_active=True, status=Vehicle.STATUS_AVAILABLE
            ).count(),
            "pending_orders": orders.filter(status=DeliveryOrder.STATUS_SCHEDULED).count(),
            "live_delivery_ids": list(live.values_list("id", flat=True)[:20]),
            "compliance_alerts": LogisticsService.compliance_alerts(),
            "weekly_deliveries": weekly,
            "weekly_fuel_costs": fuel_weekly,
        }

