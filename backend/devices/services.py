import base64
import binascii
import hashlib
import secrets
from datetime import timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from .models import (
    AuthenticationChallenge,
    DeviceEvent,
    DeviceKey,
    RegisteredDevice,
)


CHALLENGE_TTL = timedelta(minutes=5)
ENROLLMENT_PURPOSE = "DEVICE_ENROLLMENT"
DEVICE_AUTHENTICATION_PURPOSE = "DEVICE_AUTHENTICATION"
SIGNATURE_ALGORITHM = "ECDSA_P256_SHA256"


class DeviceProtocolError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def record_audit(school, actor, action, entity_type, entity_id, after_data=None):
    return AuditLog.objects.create(
        school=school,
        actor_user=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        after_data=after_data or {},
    )


def record_device_event(device, event_type, actor, action, after_data=None):
    DeviceEvent.objects.create(
        school=device.school,
        device=device,
        event_type=event_type,
        metadata={"actor_user_id": str(actor.pk) if actor else None},
    )
    return record_audit(
        school=device.school,
        actor=actor,
        action=action,
        entity_type="RegisteredDevice",
        entity_id=device.pk,
        after_data=after_data or {"status": device.status},
    )


@transaction.atomic
def issue_challenge(user, purpose, device=None):
    challenge_value = secrets.token_urlsafe(32)
    challenge = AuthenticationChallenge.objects.create(
        school=user.school,
        user=user,
        device=device,
        purpose=purpose,
        challenge_hash=digest(challenge_value),
        expires_at=timezone.now() + CHALLENGE_TTL,
    )
    record_audit(
        school=user.school,
        actor=user,
        action="DEVICE_CHALLENGE_ISSUED",
        entity_type="AuthenticationChallenge",
        entity_id=challenge.pk,
        after_data={"purpose": purpose, "device_id": str(device.pk) if device else None},
    )
    return challenge_value, challenge


def enrollment_message(challenge, user, school):
    return (
        "school-attendance:device-enrollment:v1\n"
        f"{challenge}\n{user.pk}\n{school.pk}"
    ).encode("utf-8")


def device_authentication_message(challenge, user, device):
    return (
        "school-attendance:device-authentication:v1\n"
        f"{challenge}\n{user.pk}\n{device.school_id}\n{device.pk}"
    ).encode("utf-8")


def load_public_key(public_key_pem):
    if not public_key_pem.startswith("-----BEGIN PUBLIC KEY-----"):
        raise DeviceProtocolError("Unsupported public key format.")
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as error:
        raise DeviceProtocolError("Unsupported public key format.") from error
    if not isinstance(key, EllipticCurvePublicKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise DeviceProtocolError("Unsupported public key algorithm.")

    der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    canonical_pem = key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return key, canonical_pem, hashlib.sha256(der).hexdigest()


def verify_signature(public_key, signature, message):
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
        public_key.verify(
            signature_bytes,
            message,
            ec.ECDSA(hashes.SHA256()),
        )
    except (binascii.Error, ValueError, InvalidSignature) as error:
        raise DeviceProtocolError("Invalid device signature.") from error


def device_status_for_user(user):
    if user.role != user.Role.STAFF:
        return "NOT_APPLICABLE"
    profile = getattr(user, "staff_profile", None)
    if profile is None:
        return "NOT_ENROLLED"

    active = RegisteredDevice.objects.filter(
        staff_profile=profile, status=RegisteredDevice.Status.ACTIVE
    ).exists()
    if active:
        return RegisteredDevice.Status.ACTIVE
    latest = RegisteredDevice.objects.filter(staff_profile=profile).first()
    return latest.status if latest else "NOT_ENROLLED"


def revoke_sessions(queryset, actor, reason, action="SESSION_REVOKED"):
    now = timezone.now()
    for session in queryset.select_for_update().filter(revoked_at__isnull=True):
        session.revoked_at = now
        session.save(update_fields=["revoked_at", "updated_at"])
        record_audit(
            school=session.school,
            actor=actor,
            action=action,
            entity_type="UserSession",
            entity_id=session.pk,
            after_data={
                "device_id": str(session.device_id) if session.device_id else None,
                "reason": reason,
            },
        )
    return now


def device_has_active_key(device):
    return DeviceKey.objects.filter(
        device=device, status=DeviceKey.Status.ACTIVE
    ).exists()


def device_session_is_usable(session):
    if session.device_id is None:
        return session.user.role != session.user.Role.STAFF
    key = DeviceKey.objects.filter(
        device=session.device, status=DeviceKey.Status.ACTIVE
    ).first()
    return bool(
        session.device.status == RegisteredDevice.Status.ACTIVE
        and key
        and key.algorithm == SIGNATURE_ALGORITHM
        and session.device.staff_profile.user_id == session.user_id
    )
