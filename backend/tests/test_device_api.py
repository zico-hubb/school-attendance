import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.db import close_old_connections
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from accounts.tokens import create_session
from audit.models import AuditLog
from devices.models import (
    AuthenticationChallenge,
    DeviceKey,
    RegisteredDevice,
    SessionRefreshToken,
    UserSession,
)
from devices.services import (
    ENROLLMENT_PURPOSE,
    device_authentication_message,
    enrollment_message,
    load_public_key,
)
from schools.models import School
from staff.models import StaffProfile

pytestmark = pytest.mark.django_db


PASSWORD = "School-Strong-93!"


def make_school(code):
    return School.objects.create(school_code=code, name=f"School {code}")


def make_user(school, username, role=User.Role.STAFF, active=True):
    return User.objects.create_user(
        username=username,
        password=PASSWORD,
        school=school,
        role=role,
        is_active=active,
    )


def make_staff(school, username):
    user = make_user(school, username)
    profile = StaffProfile.objects.create(
        school=school,
        user=user,
        employee_number=f"EMP-{username}",
        first_name="Ada",
        last_name="Lovelace",
        date_joined=date(2024, 1, 1),
    )
    return user, profile


def login(user, school):
    client = APIClient()
    response = client.post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {
            "school_code": school.school_code,
            "username": user.username,
            "password": PASSWORD,
        },
        format="json",
    )
    return client, response


def bearer(client, body):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")


def generate_key():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_key, public_key


def signature(private_key, message):
    return base64.b64encode(
        private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    ).decode("ascii")


def challenge(client, name="api:device-enrollment-challenge"):
    response = client.post(reverse(name, kwargs={"version": "1"}))
    assert response.status_code == 201
    return response.json()


def enrollment_request(user, school, challenge_body, private_key, public_key=None):
    public_key = public_key or private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return {
        "platform": "ANDROID",
        "device_name": "Staff phone",
        "public_key": public_key,
        "challenge": challenge_body["challenge"],
        "signature": signature(
            private_key,
            enrollment_message(challenge_body["challenge"], user, school),
        ),
    }


def enroll(user, school, client=None, private_key=None):
    if client is None:
        client, login_response = login(user, school)
        assert login_response.status_code == 200
        bearer(client, login_response.json())
    challenge_body = challenge(client)
    private_key = private_key or ec.generate_private_key(ec.SECP256R1())
    response = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        enrollment_request(user, school, challenge_body, private_key),
        format="json",
    )
    return client, private_key, challenge_body, response


def admin_client(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def decision_url(name, device):
    return reverse(
        name, kwargs={"version": "1", "device_id": device.pk}
    )


def approve_device(admin, device):
    return admin_client(admin).post(
        decision_url("api:device-approve", device), {}, format="json"
    )


def make_device(school, profile, status, private_key=None):
    private_key = private_key or ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _, canonical, fingerprint = load_public_key(public_key.decode("ascii"))
    device = RegisteredDevice.objects.create(
        school=school,
        staff_profile=profile,
        platform=RegisteredDevice.Platform.ANDROID,
        device_name="Registered phone",
        status=status,
        enrolled_at=timezone.now(),
    )
    DeviceKey.objects.create(
        school=school,
        device=device,
        public_key=canonical,
        algorithm="ECDSA_P256_SHA256",
        fingerprint=fingerprint,
        key_version=1,
        status=DeviceKey.Status.ACTIVE,
    )
    return device, private_key


def bind_device_session(user, school, private_key, device):
    client, login_response = login(user, school)
    assert login_response.status_code == 200
    bootstrap_body = login_response.json()
    bearer(client, bootstrap_body)
    challenge_response = client.post(
        reverse("api:auth-device-challenge", kwargs={"version": "1"}),
        {},
        format="json",
    )
    assert challenge_response.status_code == 201
    challenge_body = challenge_response.json()
    message = device_authentication_message(
        challenge_body["challenge"], user, device
    )
    session_response = client.post(
        reverse("api:auth-device-session", kwargs={"version": "1"}),
        {
            "challenge": challenge_body["challenge"],
            "signature": signature(private_key, message),
        },
        format="json",
    )
    return client, bootstrap_body, session_response


def test_staff_login_reports_enrollment_state_and_bootstrap_sessions_cannot_refresh():
    school = make_school("NORTH")
    user, _ = make_staff(school, "teacher")
    client, response = login(user, school)

    assert response.status_code == 200
    assert response.json()["device_status"] == "NOT_ENROLLED"
    assert response.json()["session_status"] == "BOOTSTRAP"
    refresh = client.post(
        reverse("api:auth-refresh", kwargs={"version": "1"}),
        {"refresh_token": response.json()["refresh_token"]},
        format="json",
    )
    assert refresh.status_code == 401


def test_inactive_account_is_distinguishable_only_after_correct_password():
    school = make_school("NORTH")
    inactive = make_user(school, "inactive", active=False)
    response = APIClient().post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {
            "school_code": school.school_code,
            "username": inactive.username,
            "password": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 403
    assert response.json()["state"] == "ACCOUNT_INACTIVE"
    assert UserSession.objects.filter(user=inactive).count() == 0


def test_enrollment_challenge_is_random_hashed_and_audited():
    school = make_school("NORTH")
    user, _ = make_staff(school, "teacher")
    client, response = login(user, school)
    bearer(client, response.json())

    issued = challenge(client)
    stored = AuthenticationChallenge.objects.get(
        purpose=ENROLLMENT_PURPOSE, user=user
    )

    assert issued["challenge"]
    assert issued["school_id"] == str(school.pk)
    assert stored.challenge_hash != issued["challenge"]
    assert stored.expires_at > timezone.now()
    assert AuditLog.objects.filter(
        action="DEVICE_CHALLENGE_ISSUED",
        entity_type="AuthenticationChallenge",
        entity_id=stored.pk,
        actor_user=user,
    ).exists()


def test_signed_enrollment_creates_pending_device_and_never_stores_private_or_refresh_token():
    school = make_school("NORTH")
    user, profile = make_staff(school, "teacher")
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    private_key, public_key = generate_key()
    challenge_body = challenge(client)
    payload = enrollment_request(
        user, school, challenge_body, private_key, public_key
    )

    response = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert response.status_code == 202
    device = RegisteredDevice.objects.get(staff_profile=profile)
    key = DeviceKey.objects.get(device=device)
    session = UserSession.objects.get(user=user)
    assert device.status == RegisteredDevice.Status.PENDING
    assert key.algorithm == "ECDSA_P256_SHA256"
    assert key.public_key == public_key
    assert "PRIVATE KEY" not in key.public_key
    assert payload["signature"] not in key.public_key
    assert session.refresh_token_hash != login_response.json()["refresh_token"]
    assert response.json()["state"] == "PENDING"
    assert AuditLog.objects.filter(
        action="DEVICE_ENROLLMENT_SUCCEEDED",
        entity_id=device.pk,
        actor_user=user,
    ).exists()


def test_invalid_signature_is_rejected_and_challenge_consumed():
    school = make_school("NORTH")
    user, profile = make_staff(school, "teacher")
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    challenge_body = challenge(client)
    _, public_key = generate_key()
    wrong_key, _ = generate_key()
    payload = enrollment_request(
        user, school, challenge_body, wrong_key, public_key
    )

    response = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    stored = AuthenticationChallenge.objects.get(
        purpose=ENROLLMENT_PURPOSE, user=user
    )
    assert response.status_code == 400
    assert stored.consumed_at is not None
    assert not RegisteredDevice.objects.filter(staff_profile=profile).exists()
    assert AuditLog.objects.filter(
        action="DEVICE_ENROLLMENT_REJECTED", actor_user=user
    ).exists()


def test_unsupported_public_key_algorithm_is_rejected():
    school = make_school("NORTH")
    user, profile = make_staff(school, "teacher")
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    challenge_body = challenge(client)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    payload = {
        "platform": "IOS",
        "device_name": "Staff phone",
        "public_key": public_key,
        "challenge": challenge_body["challenge"],
        "signature": base64.b64encode(b"not-a-signature").decode("ascii"),
    }

    response = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert response.status_code == 400
    assert not RegisteredDevice.objects.filter(staff_profile=profile).exists()


def test_expired_enrollment_challenge_is_rejected():
    school = make_school("NORTH")
    user, _ = make_staff(school, "teacher")
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    challenge_body = challenge(client)
    stored = AuthenticationChallenge.objects.get(
        purpose=ENROLLMENT_PURPOSE, user=user
    )
    stored.expires_at = timezone.now() - timedelta(seconds=1)
    stored.save(update_fields=["expires_at", "updated_at"])
    private_key, public_key = generate_key()
    payload = enrollment_request(
        user, school, challenge_body, private_key, public_key
    )

    response = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert response.status_code == 400
    assert not RegisteredDevice.objects.exists()


def test_reused_enrollment_challenge_is_rejected():
    school = make_school("NORTH")
    user, profile = make_staff(school, "teacher")
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    challenge_body = challenge(client)
    private_key, public_key = generate_key()
    payload = enrollment_request(
        user, school, challenge_body, private_key, public_key
    )
    first = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )
    second = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert first.status_code == 202
    assert second.status_code == 400
    assert RegisteredDevice.objects.filter(staff_profile=profile).count() == 1


@pytest.mark.parametrize("foreign_school", [False, True])
def test_enrollment_challenge_from_another_user_or_school_is_rejected(foreign_school):
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    owner, _ = make_staff(school, "owner")
    if foreign_school:
        other_user, _ = make_staff(other_school, "attacker")
        target_school = other_school
    else:
        other_user, _ = make_staff(school, "attacker")
        target_school = school

    owner_client, owner_login = login(owner, school)
    bearer(owner_client, owner_login.json())
    challenge_body = challenge(owner_client)
    other_client, other_login = login(other_user, target_school)
    bearer(other_client, other_login.json())
    private_key, public_key = generate_key()
    payload = enrollment_request(
        other_user, target_school, challenge_body, private_key, public_key
    )

    response = other_client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert response.status_code == 400
    assert not RegisteredDevice.objects.exists()


def test_enrollment_is_rejected_when_staff_already_has_an_active_device():
    school = make_school("NORTH")
    user, profile = make_staff(school, "teacher")
    make_device(school, profile, RegisteredDevice.Status.ACTIVE)
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    challenge_body = challenge(client)
    private_key, public_key = generate_key()
    payload = enrollment_request(
        user, school, challenge_body, private_key, public_key
    )

    response = client.post(
        reverse("api:device-enroll", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["state"] == "DEVICE_ALREADY_ACTIVE"
    assert RegisteredDevice.objects.filter(staff_profile=profile).count() == 1


def test_admin_can_reject_or_approve_only_pending_devices():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    user, profile = make_staff(school, "teacher")
    _, _, _, rejected_response = enroll(user, school)
    rejected_device = RegisteredDevice.objects.get(staff_profile=profile)
    reject_response = admin_client(admin).post(
        decision_url("api:device-reject", rejected_device),
        {"reason": "Device not recognized"},
        format="json",
    )
    assert rejected_response.status_code == 202
    assert reject_response.status_code == 200
    rejected_device.refresh_from_db()
    assert rejected_device.status == RegisteredDevice.Status.REJECTED
    assert rejected_device.keys.get().status == DeviceKey.Status.REVOKED

    second_user, second_profile = make_staff(school, "teacher-two")
    _, _, _, pending_response = enroll(second_user, school)
    pending = RegisteredDevice.objects.get(staff_profile=second_profile)
    approval = approve_device(admin, pending)

    assert pending_response.status_code == 202
    assert approval.status_code == 200
    pending.refresh_from_db()
    assert pending.status == RegisteredDevice.Status.ACTIVE
    assert AuditLog.objects.filter(
        action="DEVICE_APPROVED", entity_id=pending.pk, actor_user=admin
    ).exists()


def test_device_bound_session_rotation_reuse_detection_and_logout():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    user, profile = make_staff(school, "teacher")
    _, private_key, _, enrolled = enroll(user, school)
    device = RegisteredDevice.objects.get(staff_profile=profile)
    assert enrolled.status_code == 202
    assert approve_device(admin, device).status_code == 200
    client, _, bound_response = bind_device_session(
        user, school, private_key, device
    )

    assert bound_response.status_code == 200
    body = bound_response.json()
    assert body["session_status"] == "DEVICE_BOUND"
    assert body["device_status"] == "ACTIVE"
    session = UserSession.objects.get(
        refresh_token_hash=hashlib.sha256(
            body["refresh_token"].encode("utf-8")
        ).hexdigest()
    )
    assert session.device_id == device.pk
    token_record = SessionRefreshToken.objects.get(
        session=session,
        token_hash=hashlib.sha256(body["refresh_token"].encode("utf-8")).hexdigest(),
    )
    assert token_record.used_at is None
    assert not SessionRefreshToken.objects.filter(
        token_hash=body["refresh_token"]
    ).exists()

    refresh_url = reverse("api:auth-refresh", kwargs={"version": "1"})
    refreshed = client.post(
        refresh_url, {"refresh_token": body["refresh_token"]}, format="json"
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != body["refresh_token"]
    token_record.refresh_from_db()
    assert token_record.used_at is not None

    replay = client.post(
        refresh_url, {"refresh_token": body["refresh_token"]}, format="json"
    )
    assert replay.status_code == 401
    session.refresh_from_db()
    assert session.revoked_at is not None
    assert AuditLog.objects.filter(
        action="REFRESH_TOKEN_REUSE_DETECTED", entity_id=session.pk
    ).exists()

    _, _, new_bound_response = bind_device_session(
        user, school, private_key, device
    )
    assert new_bound_response.status_code == 200
    logout_client = APIClient()
    bearer(logout_client, new_bound_response.json())
    logout = logout_client.post(
        reverse("api:auth-logout", kwargs={"version": "1"})
    )
    assert logout.status_code == 204
    assert UserSession.objects.filter(
        refresh_token_hash=hashlib.sha256(
            new_bound_response.json()["refresh_token"].encode("utf-8")
        ).hexdigest(),
        revoked_at__isnull=False,
    ).exists()


def test_device_revocation_invalidates_every_bound_session_and_key():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    user, profile = make_staff(school, "teacher")
    _, private_key, _, enrolled = enroll(user, school)
    device = RegisteredDevice.objects.get(staff_profile=profile)
    assert enrolled.status_code == 202
    assert approve_device(admin, device).status_code == 200
    client, _, bound_response = bind_device_session(
        user, school, private_key, device
    )
    assert bound_response.status_code == 200
    bearer(client, bound_response.json())
    session = UserSession.objects.get(device=device)
    second_session, _ = create_session(user, device=device)
    refresh_token = bound_response.json()["refresh_token"]

    revoke = admin_client(admin).post(
        decision_url("api:device-revoke", device),
        {"reason": "Phone reported lost"},
        format="json",
    )

    assert revoke.status_code == 200
    session.refresh_from_db()
    second_session.refresh_from_db()
    device.refresh_from_db()
    assert session.revoked_at is not None
    assert second_session.revoked_at is not None
    assert device.status == RegisteredDevice.Status.REVOKED
    assert device.keys.get().status == DeviceKey.Status.REVOKED
    assert client.get(
        reverse("api:staff-list", kwargs={"version": "1"})
    ).status_code == 401
    refresh_response = APIClient().post(
        reverse("api:auth-refresh", kwargs={"version": "1"}),
        {"refresh_token": refresh_token},
        format="json",
    )
    assert refresh_response.status_code == 401


def test_account_deactivation_revokes_sessions_and_login_reports_inactive():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    user, profile = make_staff(school, "teacher")
    staff_client, login_response = login(user, school)
    session = UserSession.objects.get(user=user)
    client = admin_client(admin)

    response = client.patch(
        reverse(
            "api:staff-detail",
            kwargs={"version": "1", "staff_id": profile.pk},
        ),
        {"is_active": False},
        format="json",
    )

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.revoked_at is not None
    bearer(staff_client, login_response.json())
    assert staff_client.get(
        reverse("api:staff-list", kwargs={"version": "1"})
    ).status_code == 401
    inactive_login = APIClient().post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {
            "school_code": school.school_code,
            "username": user.username,
            "password": PASSWORD,
        },
        format="json",
    )
    assert inactive_login.status_code == 403
    assert inactive_login.json()["state"] == "ACCOUNT_INACTIVE"


def test_school_admin_device_endpoints_hide_foreign_devices():
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    foreign_user, foreign_profile = make_staff(other_school, "foreign")
    foreign_active, _ = make_device(
        other_school, foreign_profile, RegisteredDevice.Status.ACTIVE
    )
    _, foreign_pending_profile = make_staff(other_school, "foreign-pending")
    foreign_pending, _ = make_device(
        other_school, foreign_pending_profile, RegisteredDevice.Status.PENDING
    )
    client = admin_client(admin)

    listing = client.get(reverse("api:device-list", kwargs={"version": "1"}))
    assert listing.status_code == 200
    assert listing.json() == []
    assert client.get(
        decision_url("api:device-detail", foreign_active)
    ).status_code == 404
    assert client.post(
        decision_url("api:device-approve", foreign_pending), {}, format="json"
    ).status_code == 404
    assert client.post(
        decision_url("api:device-revoke", foreign_active),
        {},
        format="json",
    ).status_code == 404
    foreign_active.refresh_from_db()
    foreign_pending.refresh_from_db()
    assert foreign_active.status == RegisteredDevice.Status.ACTIVE
    assert foreign_pending.status == RegisteredDevice.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_concurrent_device_approvals_preserve_one_active_device_per_staff():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    _, profile = make_staff(school, "teacher")
    first, _ = make_device(school, profile, RegisteredDevice.Status.PENDING)
    second, _ = make_device(school, profile, RegisteredDevice.Status.PENDING)

    def approve(device):
        close_old_connections()
        try:
            client = admin_client(admin)
            return client.post(
                decision_url("api:device-approve", device), {}, format="json"
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(approve, [first, second]))

    assert sorted(results) == [200, 409]
    assert RegisteredDevice.objects.filter(
        staff_profile=profile, status=RegisteredDevice.Status.ACTIVE
    ).count() == 1


def test_device_authentication_challenge_is_single_use_and_requires_signature():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    user, profile = make_staff(school, "teacher")
    _, private_key, _, enrolled = enroll(user, school)
    device = RegisteredDevice.objects.get(staff_profile=profile)
    assert enrolled.status_code == 202
    assert approve_device(admin, device).status_code == 200
    client, login_response = login(user, school)
    bearer(client, login_response.json())
    challenge_response = client.post(
        reverse("api:auth-device-challenge", kwargs={"version": "1"}),
        {},
        format="json",
    )
    assert challenge_response.status_code == 201
    challenge_body = challenge_response.json()
    payload = {
        "challenge": challenge_body["challenge"],
        "signature": signature(
            private_key,
            device_authentication_message(
                challenge_body["challenge"], user, device
            ),
        ),
    }

    response = client.post(
        reverse("api:auth-device-session", kwargs={"version": "1"}),
        payload,
        format="json",
    )
    replay = client.post(
        reverse("api:auth-device-session", kwargs={"version": "1"}),
        payload,
        format="json",
    )

    assert response.status_code == 200
    assert replay.status_code == 401
    assert UserSession.objects.filter(user=user, device=device).count() == 1
    assert response.json()["session_status"] == "DEVICE_BOUND"


def test_admin_device_detail_includes_key_metadata_and_append_only_history():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    user, profile = make_staff(school, "teacher")
    _, _, _, enrolled = enroll(user, school)
    device = RegisteredDevice.objects.get(staff_profile=profile)
    assert enrolled.status_code == 202
    assert approve_device(admin, device).status_code == 200

    response = admin_client(admin).get(
        decision_url("api:device-detail", device)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ACTIVE"
    assert body["keys"][0]["algorithm"] == "ECDSA_P256_SHA256"
    assert any(event["event_type"] == "ENROLLMENT" for event in body["history"])
    assert any(event["action"] == "DEVICE_APPROVED" for event in body["audit_history"])
