"""Grant messaging, email, and settings permissions to all active roles."""

from django.core.management.base import BaseCommand

from apps.users.management.commands.seed_fms import grant_employee_universal_permissions


class Command(BaseCommand):
    help = "Grant messaging, email, and settings access to all employee roles"

    def handle(self, *args, **options):
        grant_employee_universal_permissions()
        self.stdout.write(
            self.style.SUCCESS(
                "Done — all active roles now have messaging, email, and settings permissions."
            )
        )
        self.stdout.write("Users must log out and log back in to refresh permissions.")
