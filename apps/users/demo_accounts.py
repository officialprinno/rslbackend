"""Demo / seed accounts used across management commands."""

from apps.users.models import Department, Permission, Role, User

DEMO_DRIVER_EMAIL = "driver@rocksolutions.co.tz"
DEMO_DRIVER_PASSWORD = "Driver@2024"
DEMO_STOREKEEPER_EMAIL = "storekeeper@rocksolutions.co.tz"
DEMO_STOREKEEPER_PASSWORD = "Storekeeper@2024"
DEMO_GM_EMAIL = "gm@rocksolutions.co.tz"
DEMO_GM_PASSWORD = "GM@2024"

ALL_BUSINESS_MODULES = [
    "inventory",
    "procurement",
    "sales",
    "logistics",
    "driver_portal",
    "production",
    "finance",
    "hr",
    "safety",
    "messaging",
    "email",
    "users",
    "settings",
]

FULL_MODULE_ACTIONS = ["create", "read", "update", "delete", "approve", "query"]


def ensure_demo_driver_user(*, reset_password: bool = True) -> User:
    """
    Ensure the demo driver portal user exists with the Driver role.

    reset_password=True always applies DEMO_DRIVER_PASSWORD (safe for dev seeds).
    """
    logistics_dept = Department.objects.filter(name="Logistics").first()
    driver_role = Role.objects.filter(name="Driver", department=logistics_dept).first()

    user, created = User.objects.get_or_create(
        email=DEMO_DRIVER_EMAIL,
        defaults={
            "first_name": "James",
            "last_name": "Mollel",
            "phone": "+255 754 000 111",
            "department": logistics_dept,
            "role": driver_role,
            "is_active": True,
        },
    )

    updates: dict = {}
    if logistics_dept and user.department_id != logistics_dept.id:
        updates["department"] = logistics_dept
    if driver_role and user.role_id != driver_role.id:
        updates["role"] = driver_role
    if not user.is_active:
        updates["is_active"] = True

    if updates:
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates.keys()))

    if reset_password or created or not user.has_usable_password():
        user.set_password(DEMO_DRIVER_PASSWORD)
        user.save(update_fields=["password"])

    return user


def ensure_gm_role_permissions(gm_role: Role) -> None:
    """General Manager — full access to every FMS module (same breadth as Super Admin)."""
    if not gm_role:
        return
    Permission.objects.filter(role=gm_role).delete()
    for module in ALL_BUSINESS_MODULES:
        for action in FULL_MODULE_ACTIONS:
            Permission.objects.update_or_create(
                role=gm_role,
                module=module,
                action=action,
                defaults={"is_active": True},
            )


def ensure_demo_gm_user(
    *,
    email: str = DEMO_GM_EMAIL,
    reset_password: bool = True,
    password: str = DEMO_GM_PASSWORD,
) -> User:
    """Ensure General Manager demo user with full module access and GM dashboard landing."""
    gm_role = Role.objects.filter(name="General Manager", department__isnull=True).first()

    user, created = User.objects.get_or_create(
        email=email.strip().lower(),
        defaults={
            "first_name": "Robert",
            "last_name": "Mkumbo",
            "phone": "+255 754 000 100",
            "department": None,
            "role": gm_role,
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        },
    )

    updates: dict = {}
    if gm_role and user.role_id != gm_role.id:
        updates["role"] = gm_role
    if user.department_id is not None:
        updates["department"] = None
    if not user.is_active:
        updates["is_active"] = True
    if user.is_superuser:
        updates["is_superuser"] = False

    if updates:
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates.keys()) + ["updated_at"])

    if gm_role:
        ensure_gm_role_permissions(gm_role)

    if reset_password or created or not user.has_usable_password():
        user.set_password(password)
        user.save(update_fields=["password"])

    return user


def ensure_storekeeper_role_permissions(storekeeper_role: Role) -> None:
    """Store operations only — inventory + employee self-service, no safety or other departments."""
    if not storekeeper_role:
        return
    allowed_modules = frozenset({"inventory", "messaging", "email", "settings"})
    Permission.objects.filter(role=storekeeper_role).exclude(module__in=allowed_modules).delete()
    for action in ("create", "read", "update", "query"):
        Permission.objects.update_or_create(
            role=storekeeper_role,
            module="inventory",
            action=action,
            defaults={"is_active": True},
        )


def ensure_demo_storekeeper_user(
    *,
    email: str = DEMO_STOREKEEPER_EMAIL,
    reset_password: bool = True,
    password: str = DEMO_STOREKEEPER_PASSWORD,
) -> User:
    """Ensure storekeeper user with Procurement Storekeeper role."""
    from apps.users.department_services import sync_user_department_assignments

    proc_dept = Department.objects.filter(name="Procurement").first()
    storekeeper_role = Role.objects.filter(
        name="Storekeeper", department=proc_dept
    ).first()

    user, created = User.objects.get_or_create(
        email=email.strip().lower(),
        defaults={
            "first_name": "Grace",
            "last_name": "Mwangi",
            "phone": "+255 754 000 222",
            "department": proc_dept,
            "role": storekeeper_role,
            "is_active": True,
        },
    )

    updates: dict = {}
    if proc_dept and user.department_id != proc_dept.id:
        updates["department"] = proc_dept
    if storekeeper_role and user.role_id != storekeeper_role.id:
        updates["role"] = storekeeper_role
    if not user.is_active:
        updates["is_active"] = True

    if updates:
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates.keys()) + ["updated_at"])

    if storekeeper_role and proc_dept:
        ensure_storekeeper_role_permissions(storekeeper_role)
        sync_user_department_assignments(
            user,
            [
                {
                    "department": proc_dept.id,
                    "role": storekeeper_role.id,
                    "is_primary": True,
                }
            ],
        )

    if reset_password or created or not user.has_usable_password():
        user.set_password(password)
        user.save(update_fields=["password"])

    return user
