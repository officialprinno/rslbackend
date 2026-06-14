"""Create or repair the demo driver portal login."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.hr.services import HRService
from apps.logistics.models import Driver
from apps.users.demo_accounts import DEMO_DRIVER_EMAIL, DEMO_DRIVER_PASSWORD, ensure_demo_driver_user
from apps.users.models import Permission, Role


def ensure_driver_role_permissions(driver_role: Role) -> None:
    """Driver portal only — no logistics or other module access."""
    if not driver_role:
        return
    Permission.objects.filter(role=driver_role).exclude(module="driver_portal").delete()
    for action in ("create", "read", "update", "query"):
        Permission.objects.get_or_create(
            role=driver_role,
            module="driver_portal",
            action=action,
            defaults={"is_active": True},
        )


class Command(BaseCommand):
    help = "Ensure driver@rocksolutions.co.tz exists with Driver role and known password"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEMO_DRIVER_PASSWORD,
            help=f"Password to set (default: {DEMO_DRIVER_PASSWORD})",
        )
        parser.add_argument(
            "--keep-password",
            action="store_true",
            help="Do not change password if the user already exists",
        )

    def handle(self, *args, **options):
        user = ensure_demo_driver_user(reset_password=not options["keep_password"])
        if user.role_id:
            ensure_driver_role_permissions(user.role)
        if options["password"] != DEMO_DRIVER_PASSWORD and not options["keep_password"]:
            user.set_password(options["password"])
            user.save(update_fields=["password"])

        hr_employee = HRService.ensure_employee_for_user(
            user,
            job_title="Driver",
            basic_salary=Decimal("650000"),
        )
        driver = Driver.objects.filter(user=user).first()
        if hr_employee and driver and driver.employee_number != hr_employee.employee_number:
            driver.employee_number = hr_employee.employee_number
            driver.save(update_fields=["employee_number", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Driver user ready: {DEMO_DRIVER_EMAIL} "
                f"(role: {user.role_name or user.role}, active: {user.is_active})"
            )
        )
        if hr_employee:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  HR employee: {hr_employee.employee_number} — {hr_employee.full_name}"
                )
            )
        if not options["keep_password"]:
            pwd = options["password"]
            self.stdout.write(f"  Password: {pwd}")
        self.stdout.write("  Portal: /driver-portal/dashboard")
