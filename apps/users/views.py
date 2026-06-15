"""
Authentication and RBAC API views for Rock Solutions FMS.
"""

from apps.core.drf_backends import FMSDjangoFilterBackend
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.audit import get_client_ip, log_audit
from apps.core.permissions import HasModulePermission, IsSuperAdmin
from apps.core.responses import api_error, api_response
from apps.users.models import ApprovalThreshold, Department, Permission, Role, User
from apps.users.password_utils import apply_user_password, clear_admin_password_record
from apps.users.serializers import (
    ApprovalThresholdSerializer,
    ChangePasswordSerializer,
    DepartmentSerializer,
    LoginSerializer,
    PermissionSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserCredentialSerializer,
    UserSerializer,
    UserUpdateSerializer,
    get_tokens_for_user,
)


class LoginView(APIView):
    """Authenticate user and return JWT tokens."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return api_error(
                message="Login failed",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = serializer.validated_data["user"]
        tokens = get_tokens_for_user(user)
        log_audit(
            user=user,
            module="auth",
            action="login",
            ip_address=get_client_ip(request),
        )
        return api_response(
            data={
                "tokens": tokens,
                "user": UserSerializer(user).data,
            },
            message="Login successful",
        )


class LogoutView(APIView):
    """Blacklist refresh token on logout."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return api_error(message="Refresh token is required.")
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return api_error(message="Invalid or expired refresh token.")
        log_audit(
            user=request.user,
            module="auth",
            action="logout",
            ip_address=get_client_ip(request),
        )
        return api_response(message="Logged out successfully")


class MeView(APIView):
    """Return the authenticated user's profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return api_response(data=UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        return api_response(data=UserSerializer(request.user).data, message="Profile updated")


class ChangePasswordView(APIView):
    """Change password for the authenticated user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        request.user.set_password(serializer.validated_data["new_password"])
        clear_admin_password_record(request.user)
        request.user.save(update_fields=["password", "admin_password"])
        log_audit(
            user=request.user,
            module="auth",
            action="change_password",
            ip_address=get_client_ip(request),
        )
        return api_response(message="Password changed successfully")


class WrappedTokenRefreshView(TokenRefreshView):
    """JWT refresh wrapped in FMS response envelope."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            from rest_framework_simplejwt.tokens import RefreshToken

            from apps.users.serializers import get_tokens_for_user

            refresh = request.data.get("refresh")
            if refresh:
                try:
                    old = RefreshToken(refresh)
                    user_id = old.get("user_id")
                    user = User.objects.filter(pk=user_id).first()
                    if user:
                        tokens = get_tokens_for_user(user)
                        return api_response(data=tokens, message="Token refreshed")
                except Exception:
                    pass
            return api_response(data=response.data, message="Token refreshed")
        return api_error(
            message="Token refresh failed",
            errors=response.data,
            status=response.status_code,
        )


class DepartmentViewSet(viewsets.ModelViewSet):
    """CRUD for departments."""

    queryset = Department.objects.select_related("hod").all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_name = "users"
    filter_backends = [FMSDjangoFilterBackend]
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    def get_required_action(self):
        if self.action in ("create",):
            return "create"
        if self.action in ("update", "partial_update"):
            return "update"
        if self.action == "destroy":
            return "delete"
        return "read"

    def get_permissions(self):
        self.required_action = self.get_required_action()
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasModulePermission()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_create(serializer)
        return api_response(
            data=serializer.data,
            message="Department created",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_update(serializer)
        return api_response(data=serializer.data, message="Department updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(message="Department deactivated")


class RoleViewSet(viewsets.ModelViewSet):
    """CRUD for roles."""

    queryset = Role.objects.select_related("department").prefetch_related("permissions").all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_name = "users"
    filter_backends = [FMSDjangoFilterBackend]
    filterset_fields = ["department", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    def get_required_action(self):
        if self.action in ("create",):
            return "create"
        if self.action in ("update", "partial_update"):
            return "update"
        if self.action == "destroy":
            return "delete"
        return "read"

    def get_permissions(self):
        self.required_action = self.get_required_action()
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasModulePermission()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_create(serializer)
        return api_response(
            data=serializer.data,
            message="Role created",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_update(serializer)
        return api_response(data=serializer.data, message="Role updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(message="Role deactivated")


class PermissionViewSet(viewsets.ModelViewSet):
    """CRUD for role permissions."""

    queryset = Permission.objects.select_related("role").all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filter_backends = [FMSDjangoFilterBackend]
    filterset_fields = ["role", "module", "action", "is_active"]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_create(serializer)
        return api_response(
            data=serializer.data,
            message="Permission created",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_update(serializer)
        return api_response(data=serializer.data, message="Permission updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return api_response(message="Permission deactivated")


class ApprovalThresholdViewSet(viewsets.ModelViewSet):
    """CRUD for approval thresholds."""

    queryset = ApprovalThreshold.objects.select_related(
        "department", "approver_role"
    ).all()
    serializer_class = ApprovalThresholdSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filter_backends = [FMSDjangoFilterBackend]
    filterset_fields = ["department", "module", "is_active"]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_create(serializer)
        return api_response(
            data=serializer.data,
            message="Approval threshold created",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_update(serializer)
        return api_response(data=serializer.data, message="Approval threshold updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        return api_response(message="Approval threshold deactivated")


class UserViewSet(viewsets.ModelViewSet):
    """CRUD for system users."""

    queryset = User.objects.select_related("department", "role").prefetch_related(
        "department_assignments__department",
        "department_assignments__role",
    ).all()
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_name = "users"
    filter_backends = [FMSDjangoFilterBackend]
    filterset_fields = ["department", "role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["last_name", "email", "created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def get_required_action(self):
        if self.action in ("create",):
            return "create"
        if self.action in ("update", "partial_update", "reset_password", "credentials"):
            return "update"
        if self.action == "destroy":
            return "delete"
        return "read"

    def get_permissions(self):
        self.required_action = self.get_required_action()
        if self.action in ("me", "update_my_preferences", "my_permissions"):
            return [IsAuthenticated()]
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasModulePermission()]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_create(serializer)
        return api_response(
            data=UserSerializer(serializer.instance).data,
            message="User created",
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_update(serializer)
        instance.refresh_from_db()
        log_audit(
            user=request.user,
            module="users",
            action="update",
            record_id=instance.id,
            new_values={"email": instance.email, "is_multi_department": instance.is_multi_department},
            ip_address=get_client_ip(request),
            department_context=instance.department_name,
        )
        return api_response(
            data=UserSerializer(instance).data,
            message="User updated",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(message="User deactivated")

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Set a new password for a user (admin / users.update permission)."""
        user = self.get_object()
        password = request.data.get("password")
        if not password:
            return api_error(message="password is required", status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            return api_error(errors={"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        apply_user_password(user, password)
        log_audit(
            user=request.user,
            module="users",
            action="reset_password",
            record_id=user.id,
            ip_address=get_client_ip(request),
        )
        return api_response(message="Password reset successfully")

    @action(
        detail=False,
        methods=["get"],
        url_path="credentials",
        permission_classes=[IsAuthenticated, IsSuperAdmin],
    )
    def credentials(self, request):
        """List email + last admin-set password for all users (super admin only)."""
        users = User.objects.select_related("role").order_by("last_name", "first_name")
        data = UserCredentialSerializer(users, many=True).data
        log_audit(
            user=request.user,
            module="users",
            action="export_credentials",
            ip_address=get_client_ip(request),
        )
        return api_response(data=data)

    @action(detail=False, methods=["get"], url_path="me/permissions")
    def my_permissions(self, request):
        from apps.users.rbac import get_merged_permissions
        from apps.users.serializers import PermissionSerializer

        perms = get_merged_permissions(request.user)
        return api_response(data=PermissionSerializer(perms, many=True).data)

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        return api_response(data=UserSerializer(request.user).data)

    @action(detail=False, methods=["patch"], url_path="me/preferences")
    def update_my_preferences(self, request):
        """Update language and theme for the authenticated user."""
        from apps.users.serializers import UserPreferencesSerializer

        serializer = UserPreferencesSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        user = request.user
        for field in ("language", "theme"):
            if field in serializer.validated_data:
                setattr(user, field, serializer.validated_data[field])
        user.save(update_fields=[f for f in ("language", "theme") if f in serializer.validated_data])
        return api_response(
            data={"language": user.language, "theme": user.theme},
            message="Preferences updated",
        )
