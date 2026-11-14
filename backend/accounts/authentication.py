from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from devices.models import UserSession
from devices.services import device_session_is_usable

from .tokens import ACCESS_TOKEN_SALT


INVALID_TOKEN_MESSAGE = "Invalid or expired access token."


class AccessTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        authorization = request.headers.get("Authorization", "")
        if not authorization:
            return None

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationFailed(INVALID_TOKEN_MESSAGE)

        try:
            payload = signing.loads(
                parts[1],
                salt=ACCESS_TOKEN_SALT,
                max_age=settings.ACCESS_TOKEN_TTL_SECONDS,
            )
            if not isinstance(payload, dict):
                raise signing.BadSignature("Invalid token payload.")

            session = UserSession.objects.select_related("user").get(
                pk=payload["session_id"],
                user_id=payload["user_id"],
                school_id=payload["school_id"],
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            DjangoValidationError,
            UserSession.DoesNotExist,
            signing.BadSignature,
        ) as error:
            raise AuthenticationFailed(INVALID_TOKEN_MESSAGE) from error

        if not session.user.is_active:
            raise AuthenticationFailed(INVALID_TOKEN_MESSAGE)
        if session.device_id and not device_session_is_usable(session):
            raise AuthenticationFailed(INVALID_TOKEN_MESSAGE)
        return session.user, session

    def authenticate_header(self, request):
        return "Bearer"
