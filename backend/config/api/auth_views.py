from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.managers import normalize_username
from accounts.models import User
from accounts.permissions import IsAuthenticated
from accounts.tokens import create_session, issue_access_token, rotate_refresh_token
from devices.models import UserSession
from devices.services import device_status_for_user, record_audit, revoke_sessions


INVALID_CREDENTIALS = "Invalid school code, username, or password."
INVALID_REFRESH_TOKEN = "Invalid or expired refresh token."


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class LoginSerializer(StrictInputSerializer):
    school_code = serializers.CharField(max_length=50)
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class RefreshSerializer(StrictInputSerializer):
    refresh_token = serializers.CharField(trim_whitespace=False, write_only=True)


class PasswordChangeSerializer(StrictInputSerializer):
    current_password = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password_confirm = serializers.CharField(
        trim_whitespace=False, write_only=True
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "The new passwords do not match."}
            )
        try:
            validate_password(attrs["new_password"], user=self.context["request"].user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"new_password": error.messages}
            ) from error
        return attrs


def token_response(session, refresh_token):
    return {
        "access_token": issue_access_token(session),
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_TTL_SECONDS,
        "refresh_expires_at": session.expires_at.isoformat(),
        "device_status": device_status_for_user(session.user),
        "password_change_required": session.user.must_change_password,
        "session_status": (
            "DEVICE_BOUND"
            if session.device_id
            else "BOOTSTRAP"
            if session.user.role == User.Role.STAFF
            else "UNBOUND"
        ),
        "user": {
            "id": str(session.user_id),
            "username": session.user.username,
            "role": session.user.role,
            "school_code": session.school.school_code,
        },
    }


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, version):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "School code, username, and password are required and must be valid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            try:
                candidate = User.objects.get(
                    school__school_code=serializer.validated_data["school_code"],
                    username=normalize_username(serializer.validated_data["username"]),
                )
            except User.DoesNotExist:
                candidate = None
            if candidate and candidate.check_password(
                serializer.validated_data["password"]
            ) and not candidate.is_active:
                return Response(
                    {
                        "state": "ACCOUNT_INACTIVE",
                        "detail": "The account is inactive.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": INVALID_CREDENTIALS},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        session, refresh_token = create_session(user)
        return Response(
            token_response(session, refresh_token),
            status=status.HTTP_200_OK,
        )


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, version):
        serializer = RefreshSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": INVALID_REFRESH_TOKEN},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = rotate_refresh_token(serializer.validated_data["refresh_token"])
        if result is None:
            return Response(
                {"detail": INVALID_REFRESH_TOKEN},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        session, refresh_token = result
        return Response(token_response(session, refresh_token))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    allow_password_change = True

    def post(self, request, version):
        with transaction.atomic():
            session = request.auth
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at", "updated_at"])
            record_audit(
                school=session.school,
                actor=request.user,
                action="SESSION_REVOKED",
                entity_type="UserSession",
                entity_id=session.pk,
                after_data={
                    "device_id": str(session.device_id) if session.device_id else None,
                    "reason": "logout",
                },
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    allow_password_change = True

    def post(self, request, version):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if not request.user.check_password(values["current_password"]):
            return Response(
                {"detail": "The current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if not user.check_password(values["current_password"]):
                return Response(
                    {"detail": "The current password is incorrect."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(values["new_password"])
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password", "updated_at"])
            revoke_sessions(
                UserSession.objects.filter(user=user).exclude(pk=request.auth.pk),
                actor=user,
                reason="password_changed",
            )
            record_audit(
                school=user.school,
                actor=user,
                action="PASSWORD_CHANGED",
                entity_type="User",
                entity_id=user.pk,
            )
        return Response(
            {"detail": "Password changed successfully.", "password_change_required": False}
        )
