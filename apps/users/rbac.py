"""Multi-department RBAC helpers."""

from __future__ import annotations

from apps.core.permissions import (
    EMPLOYEE_SELF_SERVICE_ACTIONS,
    EMPLOYEE_SELF_SERVICE_MODULES,
    GENERAL_MANAGER_ROLE,
    INTERNAL_AUDITOR_ROLE,
    SUPER_ADMIN_ROLE,
)

HOD_ROLE_PREFIX = "HOD "
HOD_INVENTORY_ACTIONS = frozenset({"read", "query"})
MACHINE_OPERATOR_ROLE = "Machine Operator"
OPERATOR_INVENTORY_ELEVATED_ROLES = frozenset({
    "Production Supervisor",
    "Production Manager",
    "General Manager",
    "Super Admin",
    "Storekeeper",
    "Store Manager",
    "Internal Auditor",
})


def is_restricted_machine_operator(user) -> bool:
    """Production floor operator — no inventory module access."""
    if not user or not user.is_authenticated or user.is_superuser:
        return False
    role_names = set(get_user_roles(user).values_list("name", flat=True))
    if MACHINE_OPERATOR_ROLE not in role_names:
        return False
    if role_names.intersection(OPERATOR_INVENTORY_ELEVATED_ROLES):
        return False
    if any(n.startswith(HOD_ROLE_PREFIX) for n in role_names):
        return False
    return True


def get_user_role_ids(user) -> set[int]:
    """Collect role IDs from primary assignment and user_departments."""
    if not user or not getattr(user, "is_authenticated", False):
        return set()
    if not user.is_authenticated:
        return set()

    from apps.users.models import UserDepartment

    role_ids = set(
        UserDepartment.objects.filter(user=user, is_active=True).values_list("role_id", flat=True)
    )
    if user.role_id:
        role_ids.add(user.role_id)
    return {rid for rid in role_ids if rid}


def get_user_roles(user):
    from apps.users.models import Role

    role_ids = get_user_role_ids(user)
    if not role_ids:
        return Role.objects.none()
    return Role.objects.filter(id__in=role_ids, is_active=True)


def get_merged_permissions(user):
    from apps.users.models import Permission

    role_ids = get_user_role_ids(user)
    if not role_ids:
        return Permission.objects.none()
    return Permission.objects.filter(role_id__in=role_ids, is_active=True).distinct()


def get_user_modules(user) -> list[str]:
    modules = list(get_merged_permissions(user).values_list("module", flat=True).distinct())
    if user_is_hod(user):
        if "inventory" not in modules:
            modules.append("inventory")
    if is_restricted_machine_operator(user):
        modules = [m for m in modules if m != "inventory"]
    modules.extend(m for m in EMPLOYEE_SELF_SERVICE_MODULES if m not in modules)
    return sorted(set(modules))


def user_is_hod(user) -> bool:
    return get_user_roles(user).filter(name__startswith=HOD_ROLE_PREFIX).exists()


def user_has_permission(user, module: str, action: str) -> bool:
    """Check module/action across all assigned department roles."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    if module in EMPLOYEE_SELF_SERVICE_MODULES and action in EMPLOYEE_SELF_SERVICE_ACTIONS:
        return True

    roles = get_user_roles(user)
    if not roles.exists():
        return False

    role_names = set(roles.values_list("name", flat=True))
    if SUPER_ADMIN_ROLE in role_names:
        return True
    if GENERAL_MANAGER_ROLE in role_names:
        return True
    if INTERNAL_AUDITOR_ROLE in role_names and action in ("read", "query"):
        return True

    if module == "inventory" and is_restricted_machine_operator(user):
        return False

    role_ids = get_user_role_ids(user)
    if get_merged_permissions(user).filter(module=module, action=action).exists():
        return True

    if module == "inventory" and action in HOD_INVENTORY_ACTIONS and user_is_hod(user):
        return True

    return False


def get_user_departments_payload(user) -> list[dict]:
    from apps.users.models import UserDepartment

    assignments = (
        UserDepartment.objects.filter(user=user, is_active=True)
        .select_related("department", "role")
        .order_by("-is_primary", "department__name")
    )
    if assignments.exists():
        return [
            {
                "department_id": row.department_id,
                "department_name": row.department.name,
                "role_id": row.role_id,
                "role": row.role.name,
                "role_name": row.role.name,
                "is_primary": row.is_primary,
            }
            for row in assignments
        ]

    if user.department_id and user.role_id:
        return [
            {
                "department_id": user.department_id,
                "department_name": user.department.name if user.department else "",
                "role_id": user.role_id,
                "role": user.role.name if user.role else "",
                "role_name": user.role.name if user.role else "",
                "is_primary": True,
            }
        ]
    return []


def get_jwt_claims(user) -> dict:
    departments = get_user_departments_payload(user)
    primary = next((d for d in departments if d["is_primary"]), departments[0] if departments else None)
    modules = get_user_modules(user)
    permissions = list(
        get_merged_permissions(user).values("module", "action").distinct()
    )
    return {
        "name": user.get_full_name(),
        "primary_department": primary["department_name"] if primary else (user.department_name or ""),
        "primary_department_id": primary["department_id"] if primary else user.department_id,
        "is_multi_department": bool(getattr(user, "is_multi_department", False)) or len(departments) > 1,
        "departments": [
            {
                "id": d["department_id"],
                "name": d["department_name"],
                "role": d["role"],
                "role_id": d["role_id"],
                "primary": d["is_primary"],
            }
            for d in departments
        ],
        "modules": modules,
        "permissions": permissions,
    }
