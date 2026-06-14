"""
Role-Based Access Control permission classes for Rock Solutions FMS.

Actions: create, read, update, delete, approve, query
"""

from rest_framework.permissions import BasePermission


MODULE_ACTIONS = ("create", "read", "update", "delete", "approve", "query")

SUPER_ADMIN_ROLE = "Super Admin"
GENERAL_MANAGER_ROLE = "General Manager"
INTERNAL_AUDITOR_ROLE = "Internal Auditor"

# Every employee can use internal messaging, personal email, and profile settings
EMPLOYEE_SELF_SERVICE_MODULES = frozenset({"messaging", "email", "settings"})
EMPLOYEE_SELF_SERVICE_ACTIONS = frozenset(
    {"create", "read", "update", "delete", "query"}
)


def user_has_permission(user, module: str, action: str) -> bool:
    """Check if user has a specific module/action permission via their role(s)."""
    from apps.users.rbac import user_has_permission as rbac_has_permission

    return rbac_has_permission(user, module, action)


class HasModulePermission(BasePermission):
    """
    ViewSet mixin permission — set `module_name` and `required_action` on the view.
    Defaults to read access.
    """

    def has_permission(self, request, view):
        module = getattr(view, "module_name", None)
        if not module:
            return request.user and request.user.is_authenticated

        action_map = {
            "GET": "read",
            "HEAD": "read",
            "OPTIONS": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }
        required = getattr(view, "required_action", None) or action_map.get(
            request.method, "read"
        )
        return user_has_permission(request.user, module, required)


class IsSuperAdmin(BasePermission):
    """Allow only Super Admin role or Django superuser."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        role = getattr(user, "role", None)
        return role and role.name == SUPER_ADMIN_ROLE
