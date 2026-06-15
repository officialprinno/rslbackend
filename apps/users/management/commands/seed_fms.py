"""
Seed initial FMS data: currencies, departments, roles, permissions, super admin.

Usage:
    python manage.py seed_fms
    python manage.py seed_fms --email admin@rocksolutions.co.tz --password Admin@2024
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Currency
from apps.users.demo_accounts import (
    DEMO_DRIVER_EMAIL,
    DEMO_GM_EMAIL,
    DEMO_STOREKEEPER_EMAIL,
    ensure_demo_driver_user,
    ensure_demo_gm_user,
    ensure_demo_storekeeper_user,
    ensure_gm_role_permissions,
)
from apps.users.password_utils import apply_user_password
from apps.users.models import Department, Permission, Role, User

DEPARTMENTS = [
    ("Finance", "Finance and accounting"),
    ("Procurement", "Purchasing and supplier management"),
    ("Sales", "Customer sales and quotations"),
    ("Logistics", "Fleet and delivery management"),
    ("Production", "Wire mesh manufacturing"),
    ("HR & Admin", "Human resources and administration"),
    ("Safety", "Workplace health and safety"),
]

CURRENCIES = [
    ("TZS", "Tanzanian Shilling", Decimal("1"), True),
    ("USD", "US Dollar", Decimal("2650"), False),
    ("EUR", "Euro", Decimal("2850"), False),
]

CROSS_DEPARTMENT_ROLES = [
    "Super Admin",
    "General Manager",
    "Internal Auditor",
]

DEPARTMENT_ROLES = {
    "Finance": ["HOD Finance", "Internal Auditor"],
    "Procurement": ["HOD Procurement", "Assistant Procurement", "Store Manager", "Storekeeper"],
    "Sales": ["HOD Sales", "Sales Officer"],
    "Logistics": ["HOD Logistics", "Logistics Officer", "Driver"],
    "Production": ["Production Manager", "Production Supervisor", "Machine Operator"],
    "HR & Admin": ["HR Officer"],
    "Safety": ["Safety Officer", "Chief Security Officer", "Security Supervisor", "Security Guard"],
}

ALL_MODULES = [
    "inventory", "procurement", "sales", "logistics", "driver_portal",
    "production", "finance", "hr", "safety", "messaging", "email", "users", "settings",
]

FULL_ACTIONS = ["create", "read", "update", "delete", "approve", "query"]
READ_QUERY_ACTIONS = ["read", "query"]
READ_APPROVE_QUERY_ACTIONS = ["read", "approve", "query"]

# All employees — messaging, personal email, profile settings
EMPLOYEE_UNIVERSAL_MODULES = {
    "messaging": ["create", "read", "update", "delete", "query"],
    "email": ["create", "read", "update", "delete", "query"],
    "settings": ["read", "update"],
    "inventory": ["read", "create"],
}

# Floor operators use production only — not universal inventory self-service
INVENTORY_UNIVERSAL_EXCLUDED_ROLES = frozenset({"Machine Operator"})


def grant_employee_universal_permissions():
    """Ensure every active role can use messaging, email, and settings."""
    for role in Role.objects.filter(is_active=True):
        for module, actions in EMPLOYEE_UNIVERSAL_MODULES.items():
            if module == "inventory" and role.name in INVENTORY_UNIVERSAL_EXCLUDED_ROLES:
                Permission.objects.filter(role=role, module="inventory").delete()
                continue
            for action in actions:
                Permission.objects.update_or_create(
                    role=role,
                    module=module,
                    action=action,
                    defaults={"is_active": True},
                )


class Command(BaseCommand):
    help = "Seed initial Rock Solutions FMS data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="admin@rocksolutions.co.tz",
            help="Super admin email",
        )
        parser.add_argument(
            "--password",
            default="Admin@2024",
            help="Super admin password",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding Rock Solutions FMS...")

        for code, name, rate, is_default in CURRENCIES:
            Currency.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "exchange_rate": rate,
                    "is_default": is_default,
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"  Currencies: {len(CURRENCIES)}"))

        dept_map = {}
        for name, description in DEPARTMENTS:
            dept, _ = Department.objects.update_or_create(
                name=name,
                defaults={"description": description, "is_active": True},
            )
            dept_map[name] = dept
        self.stdout.write(self.style.SUCCESS(f"  Departments: {len(DEPARTMENTS)}"))

        role_map = {}
        for role_name in CROSS_DEPARTMENT_ROLES:
            role, _ = Role.objects.update_or_create(
                name=role_name,
                department=None,
                defaults={"is_active": True},
            )
            role_map[role_name] = role

        for dept_name, roles in DEPARTMENT_ROLES.items():
            dept = dept_map[dept_name]
            for role_name in roles:
                if role_name == "Internal Auditor":
                    continue
                role, _ = Role.objects.update_or_create(
                    name=role_name,
                    department=dept,
                    defaults={"is_active": True},
                )
                role_map[f"{dept_name}:{role_name}"] = role

        auditor_role = role_map["Internal Auditor"]
        self.stdout.write(self.style.SUCCESS(f"  Roles: {Role.objects.count()}"))

        super_admin = role_map["Super Admin"]
        Permission.objects.filter(role=super_admin).delete()
        for module in ALL_MODULES:
            for action in FULL_ACTIONS:
                Permission.objects.create(role=super_admin, module=module, action=action)

        gm_role = role_map["General Manager"]
        ensure_gm_role_permissions(gm_role)

        Permission.objects.filter(role=auditor_role).delete()
        for module in ALL_MODULES:
            for action in READ_QUERY_ACTIONS:
                Permission.objects.create(role=auditor_role, module=module, action=action)

        hod_role_modules = [
            ("Finance:HOD Finance", ["finance"]),
            ("Procurement:HOD Procurement", ["procurement", "inventory"]),
            ("Sales:HOD Sales", ["sales"]),
            ("Logistics:HOD Logistics", ["logistics"]),
            ("Production:Production Manager", ["production", "inventory"]),
            ("Production:Production Supervisor", ["production"]),
            ("HR & Admin:HR Officer", ["hr", "users"]),
            ("Safety:Safety Officer", ["safety"]),
        ("Safety:Chief Security Officer", ["safety"]),
        ("Safety:Security Supervisor", ["safety"]),
        ("Safety:Security Guard", ["safety"]),
        ]
        for role_key, modules in hod_role_modules:
            role = role_map.get(role_key)
            if not role:
                continue
            Permission.objects.filter(role=role).delete()
            for module in modules:
                for action in FULL_ACTIONS:
                    Permission.objects.create(role=role, module=module, action=action)

        storekeeper_role = role_map.get("Procurement:Storekeeper")
        if storekeeper_role:
            Permission.objects.filter(role=storekeeper_role).delete()
            for action in ("create", "read", "update", "query"):
                Permission.objects.create(
                    role=storekeeper_role,
                    module="inventory",
                    action=action,
                )

        assistant_role = role_map.get("Procurement:Assistant Procurement")
        if assistant_role:
            Permission.objects.filter(role=assistant_role).delete()
            for module in ("procurement", "inventory"):
                for action in ("create", "read", "update", "approve", "query"):
                    Permission.objects.create(
                        role=assistant_role,
                        module=module,
                        action=action,
                    )

        store_manager_role = role_map.get("Procurement:Store Manager")
        if store_manager_role:
            Permission.objects.filter(role=store_manager_role).delete()
            for action in ("create", "read", "update", "approve", "query"):
                Permission.objects.create(
                    role=store_manager_role,
                    module="inventory",
                    action=action,
                )
            for action in ("create", "read", "update", "query"):
                Permission.objects.create(
                    role=store_manager_role,
                    module="procurement",
                    action=action,
                )

        coordinator_role = Role.objects.filter(
            name="Coordinator", department=dept_map.get("Procurement")
        ).first()
        if coordinator_role and not assistant_role:
            Permission.objects.filter(role=coordinator_role).delete()
            for module in ("procurement", "inventory"):
                for action in ("create", "read", "update", "approve", "query"):
                    Permission.objects.create(
                        role=coordinator_role,
                        module=module,
                        action=action,
                    )

        from apps.users.models import ApprovalThreshold

        proc_dept = dept_map.get("Procurement")
        hod_proc = role_map.get("Procurement:HOD Procurement")
        asst_proc = assistant_role or coordinator_role
        if proc_dept and hod_proc and asst_proc:
            ApprovalThreshold.objects.update_or_create(
                department=proc_dept,
                module="inventory",
                min_amount=Decimal("0"),
                defaults={
                    "max_amount": Decimal("500000"),
                    "approver_role": asst_proc,
                    "is_active": True,
                },
            )
            ApprovalThreshold.objects.update_or_create(
                department=proc_dept,
                module="inventory",
                min_amount=Decimal("500000.01"),
                defaults={
                    "max_amount": None,
                    "approver_role": hod_proc,
                    "is_active": True,
                },
            )

        sales_officer_role = role_map.get("Sales:Sales Officer")
        if sales_officer_role:
            Permission.objects.filter(role=sales_officer_role).delete()
            for action in ("create", "read", "update", "query"):
                Permission.objects.create(
                    role=sales_officer_role,
                    module="sales",
                    action=action,
                )

        logistics_officer_role = role_map.get("Logistics:Logistics Officer")
        if logistics_officer_role:
            Permission.objects.filter(role=logistics_officer_role).delete()
            for action in ("create", "read", "update", "query"):
                Permission.objects.create(
                    role=logistics_officer_role,
                    module="logistics",
                    action=action,
                )

        driver_role = role_map.get("Logistics:Driver")
        if driver_role:
            Permission.objects.filter(role=driver_role).delete()
            for action in ("create", "read", "update", "query"):
                Permission.objects.create(
                    role=driver_role,
                    module="driver_portal",
                    action=action,
                )

        machine_operator_role = role_map.get("Production:Machine Operator")
        if machine_operator_role:
            Permission.objects.filter(role=machine_operator_role).delete()
            for action in ("read", "update", "query"):
                Permission.objects.create(
                    role=machine_operator_role,
                    module="production",
                    action=action,
                )
            Permission.objects.filter(role=machine_operator_role, module="inventory").delete()

        production_supervisor_role = role_map.get("Production:Production Supervisor")
        if production_supervisor_role:
            Permission.objects.filter(role=production_supervisor_role).delete()
            for action in ("create", "read", "update", "approve", "query"):
                Permission.objects.create(
                    role=production_supervisor_role,
                    module="production",
                    action=action,
                )

        admin_role = role_map["Super Admin"]
        user, created = User.objects.update_or_create(
            email=options["email"],
            defaults={
                "first_name": "System",
                "last_name": "Administrator",
                "role": admin_role,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created or options.get("password"):
            apply_user_password(user, options["password"])

        grant_employee_universal_permissions()
        self.stdout.write(self.style.SUCCESS("  Employee modules: messaging, email, settings → all roles"))

        driver_user = ensure_demo_driver_user(reset_password=True)
        self.stdout.write(self.style.SUCCESS(f"  Driver portal user: {driver_user.email} ({DEMO_DRIVER_EMAIL})"))

        storekeeper_user = ensure_demo_storekeeper_user(reset_password=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Storekeeper user: {storekeeper_user.email} ({DEMO_STOREKEEPER_EMAIL})"
            )
        )

        gm_user = ensure_demo_gm_user(reset_password=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"  General Manager: {gm_user.email} ({DEMO_GM_EMAIL}) — password GM@2024, portal /dashboard"
            )
        )

        self.stdout.write(self.style.SUCCESS(f"  Super admin: {user.email}"))
        from apps.inventory.seeders.master_inventory import seed_master_inventory

        tzs = Currency.objects.filter(code="TZS").first()
        if tzs:
            inv_stats = seed_master_inventory(currency=tzs, update=False)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Master inventory: {inv_stats['categories_created']} categories, "
                    f"{inv_stats['items_created']} items"
                )
            )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("  Next: python manage.py seed_procurement  (sample suppliers & PRs)")
