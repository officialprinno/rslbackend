"""Serializers for users and RBAC."""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import ApprovalThreshold, Department, Permission, Role, User, UserDepartment
from apps.users.rbac import get_jwt_claims, get_merged_permissions, get_user_departments_payload, get_user_modules
from apps.users.department_services import sync_user_department_assignments


class DepartmentSerializer(serializers.ModelSerializer):
    hod_name = serializers.CharField(source="hod.get_full_name", read_only=True)
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "description",
            "hod",
            "hod_name",
            "user_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_user_count(self, obj):
        return obj.users.filter(is_active=True).count()


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "module", "action", "role", "is_active", "created_at"]
        read_only_fields = ["created_at"]


class RoleSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    permissions = PermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = [
            "id",
            "name",
            "department",
            "department_name",
            "permissions",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class RoleMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name"]


class ApprovalThresholdSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    approver_role_name = serializers.CharField(source="approver_role.name", read_only=True)

    class Meta:
        model = ApprovalThreshold
        fields = [
            "id",
            "department",
            "department_name",
            "module",
            "min_amount",
            "max_amount",
            "approver_role",
            "approver_role_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserDepartmentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = UserDepartment
        fields = [
            "id",
            "department",
            "department_name",
            "role",
            "role_name",
            "is_primary",
        ]


class UserDepartmentWriteSerializer(serializers.Serializer):
    department = serializers.IntegerField()
    role = serializers.IntegerField()
    is_primary = serializers.BooleanField(default=False)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    role_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(read_only=True)
    departments = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()
    primary_department = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "profile_photo",
            "department",
            "department_name",
            "role",
            "role_name",
            "is_multi_department",
            "departments",
            "primary_department",
            "permissions",
            "modules",
            "is_active",
            "is_staff",
            "language",
            "theme",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "is_staff"]

    def get_departments(self, obj):
        return get_user_departments_payload(obj)

    def get_permissions(self, obj):
        return list(get_merged_permissions(obj).values("module", "action").distinct())

    def get_modules(self, obj):
        return get_user_modules(obj)

    def get_primary_department(self, obj):
        departments = get_user_departments_payload(obj)
        primary = next((d for d in departments if d["is_primary"]), departments[0] if departments else None)
        return primary["department_name"] if primary else obj.department_name


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    department_assignments = UserDepartmentWriteSerializer(many=True, required=False)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "first_name",
            "last_name",
            "phone",
            "department",
            "role",
            "is_active",
            "is_multi_department",
            "department_assignments",
        ]

    def create(self, validated_data):
        assignments = validated_data.pop("department_assignments", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if assignments:
            sync_user_department_assignments(user, assignments)
        elif user.department_id and user.role_id:
            sync_user_department_assignments(
                user,
                [
                    {
                        "department": user.department_id,
                        "role": user.role_id,
                        "is_primary": True,
                    }
                ],
            )
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    department_assignments = UserDepartmentWriteSerializer(many=True, required=False)

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "profile_photo",
            "department",
            "role",
            "is_active",
            "is_multi_department",
            "department_assignments",
        ]

    def update(self, instance, validated_data):
        assignments = validated_data.pop("department_assignments", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if assignments is not None:
            sync_user_department_assignments(instance, assignments)
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class UserPreferencesSerializer(serializers.Serializer):
    language = serializers.ChoiceField(choices=["en", "sw"], required=False)
    theme = serializers.ChoiceField(choices=["dark", "light"], required=False)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        user = authenticate(
            request=self.context.get("request"),
            username=email,
            password=password,
        )
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been deactivated.")
        attrs["user"] = user
        return attrs


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


def get_tokens_for_user(user):
    """Generate JWT refresh + access tokens with multi-department claims."""
    refresh = RefreshToken.for_user(user)
    claims = get_jwt_claims(user)
    for key, value in claims.items():
        refresh[key] = value
        refresh.access_token[key] = value
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }
