from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import ApprovalThreshold, Department, Permission, Role, User, UserDepartment


class UserDepartmentInline(admin.TabularInline):
    model = UserDepartment
    extra = 0
    autocomplete_fields = ("department", "role")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "hod", "is_active", "created_at")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "is_active", "created_at")
    search_fields = ("name",)
    list_filter = ("department", "is_active")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "module", "action", "is_active")
    list_filter = ("module", "action", "role", "is_active")


@admin.register(ApprovalThreshold)
class ApprovalThresholdAdmin(admin.ModelAdmin):
    list_display = ("department", "module", "min_amount", "max_amount", "approver_role", "is_active")
    list_filter = ("department", "module", "is_active")


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "role", "is_primary", "is_active")
    list_filter = ("department", "is_primary", "is_active")
    search_fields = ("user__email", "user__first_name", "user__last_name", "department__name")
    autocomplete_fields = ("user", "department", "role")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = (
        "email",
        "first_name",
        "last_name",
        "department",
        "role",
        "is_multi_department",
        "is_active",
        "is_staff",
    )
    list_filter = ("is_active", "is_staff", "is_multi_department", "department", "role")
    search_fields = ("email", "first_name", "last_name")
    inlines = [UserDepartmentInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "profile_photo")}),
        ("Organization", {"fields": ("department", "role", "is_multi_department")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "department",
                    "role",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )
