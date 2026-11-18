from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.managers import normalize_username
from accounts.models import User
from devices.models import UserSession
from devices.services import record_audit, revoke_sessions
from schools.models import Department

from .models import StaffProfile


class StaffSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    must_change_password = serializers.BooleanField(
        source="user.must_change_password", read_only=True
    )
    role = serializers.CharField(source="user.role", read_only=True)
    department = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "user_id",
            "username",
            "email",
            "phone",
            "role",
            "is_active",
            "must_change_password",
            "employee_number",
            "first_name",
            "last_name",
            "department",
            "job_title",
            "employment_status",
            "date_joined",
            "date_left",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SchoolScopedSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class StaffCreateSerializer(SchoolScopedSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    email = serializers.EmailField(allow_blank=True, required=False)
    phone = serializers.CharField(max_length=32, allow_blank=True, required=False)
    employee_number = serializers.CharField(max_length=64)
    first_name = serializers.CharField(max_length=120)
    last_name = serializers.CharField(max_length=120)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.none(), allow_null=True, required=False
    )
    job_title = serializers.CharField(max_length=120, allow_blank=True, required=False)
    date_joined = serializers.DateField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context["request"].user.school
        self.fields["department"].queryset = Department.objects.filter(
            school=school, is_active=True
        )

    def validate(self, attrs):
        user = self.context["request"].user
        username = normalize_username(attrs["username"])
        if User.objects.filter(school=user.school, username=username).exists():
            raise serializers.ValidationError(
                {"username": "A user with this username already exists in this school."}
            )
        if StaffProfile.objects.filter(
            school=user.school, employee_number=attrs["employee_number"]
        ).exists():
            raise serializers.ValidationError(
                {"employee_number": "This employee number already exists in this school."}
            )
        password_user = User(username=username, school=user.school)
        try:
            validate_password(attrs["password"], user=password_user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"password": error.messages}
            ) from error
        return attrs

    def create(self, validated_data):
        request_user = self.context["request"].user
        with transaction.atomic():
            password = validated_data.pop("password")
            username = validated_data.pop("username")
            email = validated_data.pop("email", "")
            phone = validated_data.pop("phone", "")
            user = User.objects.create_user(
                username=username,
                password=password,
                school=request_user.school,
                email=email,
                phone=phone,
                role=User.Role.STAFF,
                must_change_password=True,
            )
            return StaffProfile.objects.create(
                school=request_user.school,
                user=user,
                **validated_data,
            )


class StaffUpdateSerializer(SchoolScopedSerializer):
    email = serializers.EmailField(allow_blank=True, required=False)
    phone = serializers.CharField(max_length=32, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)
    employee_number = serializers.CharField(max_length=64, required=False)
    first_name = serializers.CharField(max_length=120, required=False)
    last_name = serializers.CharField(max_length=120, required=False)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.none(), allow_null=True, required=False
    )
    job_title = serializers.CharField(max_length=120, allow_blank=True, required=False)
    employment_status = serializers.ChoiceField(
        choices=StaffProfile.EmploymentStatus.choices, required=False
    )
    date_joined = serializers.DateField(required=False)
    date_left = serializers.DateField(allow_null=True, required=False)
    temporary_password = serializers.CharField(
        write_only=True, trim_whitespace=False, required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self.context["request"].user.school
        self.fields["department"].queryset = Department.objects.filter(
            school=school, is_active=True
        )

    def validate(self, attrs):
        if "employee_number" in attrs and StaffProfile.objects.filter(
            school=self.instance.school,
            employee_number=attrs["employee_number"],
        ).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError(
                {"employee_number": "This employee number already exists in this school."}
            )
        if "temporary_password" in attrs:
            try:
                validate_password(attrs["temporary_password"], user=self.instance.user)
            except DjangoValidationError as error:
                raise serializers.ValidationError(
                    {"temporary_password": error.messages}
                ) from error
        return attrs

    def update(self, instance, validated_data):
        user_fields = {"email", "phone", "is_active"}
        temporary_password = validated_data.pop("temporary_password", None)
        user_updates = {
            field: validated_data.pop(field)
            for field in list(validated_data)
            if field in user_fields
        }
        with transaction.atomic():
            for field, value in validated_data.items():
                setattr(instance, field, value)
            if validated_data:
                instance.save()
            for field, value in user_updates.items():
                setattr(instance.user, field, value)
            if temporary_password is not None:
                instance.user.set_password(temporary_password)
                instance.user.must_change_password = True
            if user_updates or temporary_password is not None:
                deactivating = user_updates.get("is_active") is False
                if deactivating or temporary_password is not None:
                    revoke_sessions(
                        UserSession.objects.filter(user=instance.user),
                        actor=self.context["request"].user,
                        reason=(
                            "account_deactivated"
                            if deactivating
                            else "temporary_password_reset"
                        ),
                    )
                instance.user.save()
                if temporary_password is not None:
                    record_audit(
                        school=instance.school,
                        actor=self.context["request"].user,
                        action="STAFF_TEMPORARY_PASSWORD_RESET",
                        entity_type="User",
                        entity_id=instance.user_id,
                    )
        return instance


def save_staff(serializer):
    try:
        return serializer.save()
    except IntegrityError as error:
        raise serializers.ValidationError(
            {"detail": "A username or employee number already exists in this school."}
        ) from error
