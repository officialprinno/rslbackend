"""
User, RBAC, and organizational models for Rock Solutions FMS.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.core.models import BaseModel
from apps.users.managers import UserManager


class Department(BaseModel):
    """Organizational department (Finance, Procurement, Sales, etc.)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    hod = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_departments",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Role(BaseModel):
    """Role within a department (HOD, Officer, Auditor, etc.)."""

    name = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="roles",
        null=True,
        blank=True,
        help_text="Null for cross-department roles (e.g. Super Admin, GM)",
    )

    class Meta:
        ordering = ["name"]
        unique_together = [("name", "department")]

    def __str__(self):
        if self.department:
            return f"{self.name} ({self.department.name})"
        return self.name


class Permission(BaseModel):
    """RBAC permission: module + action assigned to a role."""

    MODULE_CHOICES = [
        ("inventory", "Inventory"),
        ("procurement", "Procurement"),
        ("sales", "Sales"),
        ("logistics", "Logistics"),
        ("driver_portal", "Driver Portal"),
        ("production", "Production"),
        ("finance", "Finance"),
        ("hr", "HR"),
        ("safety", "Safety"),
        ("messaging", "Messaging"),
        ("email", "Email"),
        ("users", "Users"),
        ("settings", "Settings"),
    ]

    ACTION_CHOICES = [
        ("create", "Create"),
        ("read", "Read"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("approve", "Approve"),
        ("query", "Query"),
    ]

    module = models.CharField(max_length=50, choices=MODULE_CHOICES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="permissions",
    )

    class Meta:
        ordering = ["module", "action"]
        unique_together = [("module", "action", "role")]

    def __str__(self):
        return f"{self.role.name}: {self.module}.{self.action}"


class ApprovalThreshold(BaseModel):
    """Configurable approval routing by amount range."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="approval_thresholds",
    )
    module = models.CharField(max_length=50)
    min_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    max_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Null means no upper limit",
    )
    approver_role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="approval_thresholds",
    )

    class Meta:
        ordering = ["department", "module", "min_amount"]

    def __str__(self):
        max_label = self.max_amount if self.max_amount is not None else "∞"
        return f"{self.department.name}/{self.module}: {self.min_amount}–{max_label} → {self.approver_role.name}"


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Custom user model — email is the login identifier."""

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    profile_photo = models.ImageField(upload_to="profiles/", null=True, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Primary department (display/default)",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Primary role (legacy; merged with user_departments at runtime)",
    )
    is_multi_department = models.BooleanField(
        default=False,
        help_text="User manages multiple departments via user_departments",
    )
    is_staff = models.BooleanField(default=False)
    language = models.CharField(
        max_length=5,
        choices=[("en", "English"), ("sw", "Swahili")],
        default="en",
    )
    theme = models.CharField(
        max_length=5,
        choices=[("dark", "Dark"), ("light", "Light")],
        default="light",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def role_name(self):
        return self.role.name if self.role else None

    @property
    def department_name(self):
        return self.department.name if self.department else None


class UserDepartment(BaseModel):
    """Multi-department role assignment for a user."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="department_assignments",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="user_assignments",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="user_departments",
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "department__name"]
        unique_together = [("user", "department")]

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.role.name} @ {self.department.name}"
