"""Auth and RBAC URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.users.views import (
    ApprovalThresholdViewSet,
    ChangePasswordView,
    DepartmentViewSet,
    LoginView,
    LogoutView,
    MeView,
    PermissionViewSet,
    RoleViewSet,
    UserViewSet,
    WrappedTokenRefreshView,
)

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("approval-thresholds", ApprovalThresholdViewSet, basename="approval-threshold")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("refresh/", WrappedTokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("", include(router.urls)),
]
