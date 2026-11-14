from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.managers import normalize_username
from accounts.models import User
from accounts.tokens import create_session, issue_access_token, rotate_refresh_token
from devices.services import device_status_for_user, record_audit


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


def token_response(session, refresh_token):
    return {
        "access_token": issue_access_token(session),
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.ACCESS_TOKEN_TTL_SECONDS,
        "refresh_expires_at": session.expires_at.isoformat(),
        "device_status": device_status_for_user(session.user),
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
