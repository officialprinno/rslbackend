"""
Seed sample logistics data: vehicles, drivers, delivery orders.

Prerequisites:
    python manage.py migrate
    python manage.py seed_fms
    python manage.py seed_sales
    python manage.py seed_logistics
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import Warehouse
from apps.logistics.models import (
    DeliveryOrder,
    DeliveryOrderItem,
    Driver,
    FuelRecord,
    Vehicle,
    VehicleMaintenance,
)
from apps.logistics.utils import generate_document_number
from apps.sales.models import SalesOrder
from apps.users.demo_accounts import ensure_demo_driver_user
from apps.users.models import Department, Role, User

SAMPLE_VEHICLES = [
    {
        "registration_number": "T 123 ABC",
        "make": "Isuzu",
        "model": "FVZ",
        "year": 2021,
        "vehicle_type": Vehicle.TYPE_TRUCK,
        "capacity_kg": Decimal("15000"),
        "color": "White",
        "status": Vehicle.STATUS_AVAILABLE,
    },
    {
        "registration_number": "T 456 DEF",
        "make": "Toyota",
        "model": "Hilux",
        "year": 2023,
        "vehicle_type": Vehicle.TYPE_PICKUP,
        "capacity_kg": Decimal("1200"),
        "color": "Silver",
        "status": Vehicle.STATUS_AVAILABLE,
    },
    {
        "registration_number": "T 789 GHI",
        "make": "Mercedes",
        "model": "Actros",
        "year": 2020,
        "vehicle_type": Vehicle.TYPE_TRUCK,
        "capacity_kg": Decimal("25000"),
        "color": "Blue",
        "status": Vehicle.STATUS_MAINTENANCE,
    },
]


class Command(BaseCommand):
    help = "Seed sample vehicles, drivers, and delivery orders"

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(email="admin@rocksolutions.co.tz").first()
        if not admin:
            self.stdout.write(self.style.ERROR("Run seed_fms first."))
            return

        logistics_dept = Department.objects.filter(name="Logistics").first()
        driver_role = (
            Role.objects.filter(name="Driver", department=logistics_dept).first()
            or Role.objects.filter(name="Logistics Officer", department=logistics_dept).first()
        )
        warehouse = Warehouse.objects.filter(is_active=True).first()
        if not warehouse:
            warehouse = Warehouse.objects.create(name="Main Warehouse", location="Mwanza")

        today = timezone.now().date()
        expiry = today + timedelta(days=365)

        for vdata in SAMPLE_VEHICLES:
            vdata.setdefault("insurance_expiry", expiry)
            vdata.setdefault("road_licence_expiry", expiry)
            vdata.setdefault("last_service_date", today - timedelta(days=90))
            vdata.setdefault("next_service_date", today + timedelta(days=30))
            vdata.setdefault("odometer_reading", 45000)
            vehicle, created = Vehicle.objects.update_or_create(
                registration_number=vdata["registration_number"],
                defaults=vdata,
            )
            self.stdout.write(f"  {'Created' if created else 'Updated'} vehicle: {vehicle.registration_number}")

        driver_user = ensure_demo_driver_user(reset_password=True)

        truck = Vehicle.objects.filter(registration_number="T 123 ABC").first()
        driver, created = Driver.objects.update_or_create(
            license_number="DL-2020-88421",
            defaults={
                "user": driver_user,
                "employee_number": "EMP-DRV-001",
                "license_class": Driver.CLASS_CE,
                "license_expiry": expiry,
                "medical_expiry": expiry,
                "is_available": True,
                "availability_status": Driver.AVAIL_AVAILABLE,
                "assigned_vehicle": truck,
            },
        )
        from apps.hr.services import HRService

        hr_employee = HRService.ensure_employee_for_user(
            driver_user,
            job_title="Driver",
            basic_salary=Decimal("650000"),
        )
        if hr_employee and driver.employee_number != hr_employee.employee_number:
            driver.employee_number = hr_employee.employee_number
            driver.save(update_fields=["employee_number", "updated_at"])
        self.stdout.write(f"  {'Created' if created else 'Updated'} driver: {driver}")
        if hr_employee:
            self.stdout.write(f"  HR employee: {hr_employee.employee_number} — {hr_employee.full_name}")

        so = SalesOrder.objects.filter(
            status__in=[SalesOrder.STATUS_CONFIRMED, SalesOrder.STATUS_PROCESSING],
            is_active=True,
        ).first()

        if so and truck:
            scheduled = timezone.now() + timedelta(days=2)
            do, created = DeliveryOrder.objects.get_or_create(
                sales_order=so,
                status=DeliveryOrder.STATUS_SCHEDULED,
                defaults={
                    "do_number": generate_document_number("DO", DeliveryOrder, "do_number"),
                    "vehicle": truck,
                    "driver": driver,
                    "origin_warehouse": warehouse,
                    "destination": so.delivery_address or so.customer.address,
                    "customer": so.customer,
                    "scheduled_date": scheduled,
                    "distance_km": Decimal("320"),
                    "trip_status": DeliveryOrder.TRIP_ASSIGNED,
                    "created_by": admin,
                },
            )
            if created:
                for so_item in so.items.all():
                    remaining = so_item.quantity_ordered - so_item.quantity_delivered
                    if remaining > 0:
                        DeliveryOrderItem.objects.create(
                            delivery_order=do,
                            so_item=so_item,
                            item=so_item.item,
                            quantity=remaining,
                        )
            self.stdout.write(f"  Delivery order: {do.do_number}")

        if truck:
            FuelRecord.objects.get_or_create(
                vehicle=truck,
                date=today - timedelta(days=3),
                defaults={
                    "driver": driver,
                    "liters": Decimal("120"),
                    "cost_per_liter": Decimal("2950"),
                    "total_cost": Decimal("354000"),
                    "odometer_reading": 44800,
                    "station_name": "Total Energies Mwanza",
                    "recorded_by": admin,
                },
            )
            VehicleMaintenance.objects.get_or_create(
                vehicle=Vehicle.objects.get(registration_number="T 789 GHI"),
                maintenance_type=VehicleMaintenance.TYPE_SERVICE,
                status=VehicleMaintenance.STATUS_SCHEDULED,
                defaults={
                    "description": "Scheduled 10,000 km service",
                    "cost": Decimal("850000"),
                    "service_date": today + timedelta(days=5),
                    "performed_by": "Mwanza Auto Garage",
                },
            )

        self.stdout.write(self.style.SUCCESS("Logistics seed complete."))
