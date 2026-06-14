"""Role checks for production execution workflow."""

from apps.core.permissions import user_has_permission

PRODUCTION_MANAGER_ROLE = "Production Manager"
PRODUCTION_SUPERVISOR_ROLE = "Production Supervisor"
MACHINE_OPERATOR_ROLE = "Machine Operator"
STOREKEEPER_ROLE = "Storekeeper"


def _user_role_names(user) -> set[str]:
    from apps.users.rbac import get_user_roles

    return set(get_user_roles(user).values_list("name", flat=True))


def is_machine_operator(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    return MACHINE_OPERATOR_ROLE in _user_role_names(user)


def is_production_supervisor(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    roles = _user_role_names(user)
    return bool(
        roles
        & {
            PRODUCTION_MANAGER_ROLE,
            PRODUCTION_SUPERVISOR_ROLE,
            "General Manager",
            "Super Admin",
        }
    )


def is_storekeeper(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    roles = _user_role_names(user)
    return STOREKEEPER_ROLE in roles or "Store Manager" in roles


def can_manage_work_orders(user) -> bool:
    if user.is_superuser:
        return True
    if is_machine_operator(user):
        return False
    return user_has_permission(user, "production", "create")


def can_assign_operator(user) -> bool:
    return is_production_supervisor(user) or user_has_permission(user, "production", "approve")


def can_operate_assigned_work_order(user, work_order) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or is_production_supervisor(user):
        return True
    if is_machine_operator(user):
        return work_order.operator_id == user.id
    return user_has_permission(user, "production", "update")


def can_approve_production_completion(user) -> bool:
    return is_production_supervisor(user) or user_has_permission(user, "production", "approve")


def can_receive_finished_goods(user) -> bool:
    if user.is_superuser:
        return True
    if is_storekeeper(user):
        return user_has_permission(user, "inventory", "create") or user_has_permission(
            user, "inventory", "update"
        )
    return is_production_supervisor(user) and user_has_permission(user, "inventory", "read")


def can_use_legacy_production_start(user, work_order) -> bool:
    """Legacy immediate-inventory start — production managers only."""
    if work_order.execution_workflow:
        return False
    if user.is_superuser:
        return True
    return not is_machine_operator(user) and user_has_permission(user, "production", "create")
