import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from devices.models import SessionRefreshToken, UserSession
from devices.services import (
    device_session_is_usable,
    record_audit,
    revoke_sessions,
)


ACCESS_TOKEN_SALT = "school-attendance.access-token"


def hash_refresh_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@transaction.atomic
def create_session(user, device=None):
    refresh_token = secrets.token_urlsafe(48)
    now = timezone.now()
    session = UserSession.objects.create(
        school=user.school,
        user=user,
        device=device,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=now
        + timedelta(seconds=settings.REFRESH_TOKEN_TTL_SECONDS),
    )
    SessionRefreshToken.objects.create(
        school=user.school,
        session=session,
        token_hash=hash_refresh_token(refresh_token),
    )
    record_audit(
        school=user.school,
        actor=user,
        action="SESSION_CREATED",
        entity_type="UserSession",
        entity_id=session.pk,
        after_data={"device_id": str(device.pk) if device else None},
    )
    return session, refresh_token


def issue_access_token(session):
    return signing.dumps(
        {
            "user_id": str(session.user_id),
            "school_id": str(session.school_id),
            "session_id": str(session.pk),
        },
        salt=ACCESS_TOKEN_SALT,
        compress=True,
    )


def rotate_refresh_token(token):
    token_hash = hash_refresh_token(token)
    with transaction.atomic():
        session = (
            SessionRefreshToken.objects.select_for_update(of=("self",))
            .select_related("session__user", "session__device")
            .filter(token_hash=token_hash)
            .first()
        )
        now = timezone.now()
        if session is None:
            return None

        user_session = (
            UserSession.objects.select_for_update(of=("self",))
            .select_related("user", "device")
            .get(pk=session.session_id)
        )
        if session.used_at is not None:
            record_audit(
                school=user_session.school,
                actor=user_session.user,
                action="REFRESH_TOKEN_REUSE_DETECTED",
                entity_type="UserSession",
                entity_id=user_session.pk,
                after_data={"token_family_id": str(user_session.token_family_id)},
            )
            revoke_sessions(
                UserSession.objects.filter(
                    token_family_id=user_session.token_family_id
                ),
                actor=user_session.user,
                reason="refresh_token_reuse",
                action="REFRESH_TOKEN_REUSE_SESSION_REVOKED",
            )
            return None

        if (
            user_session.revoked_at is not None
            or user_session.expires_at <= now
            or not user_session.user.is_active
            or user_session.refresh_token_hash != token_hash
            or not device_session_is_usable(user_session)
        ):
            return None

        replacement = secrets.token_urlsafe(48)
        session.used_at = now
        session.save(update_fields=["used_at"])
        user_session.refresh_token_hash = hash_refresh_token(replacement)
        user_session.last_used_at = now
        user_session.save(
            update_fields=["refresh_token_hash", "last_used_at", "updated_at"]
        )
        SessionRefreshToken.objects.create(
            school=user_session.school,
            session=user_session,
            token_hash=hash_refresh_token(replacement),
        )
        record_audit(
            school=user_session.school,
            actor=user_session.user,
            action="SESSION_REFRESHED",
            entity_type="UserSession",
            entity_id=user_session.pk,
            after_data={
                "device_id": (
                    str(user_session.device_id) if user_session.device_id else None
                )
            },
        )
        return user_session, replacement
