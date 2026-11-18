from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAuthenticated, IsSchoolAdmin
from accounts.tokens import create_session
from audit.models import AuditLog
from devices.models import (
    AuthenticationChallenge,
    DeviceEvent,
    DeviceKey,
    RegisteredDevice,
    UserSession,
)
from devices.services import (
    DEVICE_AUTHENTICATION_PURPOSE,
    ENROLLMENT_PURPOSE,
    SIGNATURE_ALGORITHM,
    DeviceProtocolError,
    device_authentication_message,
    device_has_active_key,
    digest,
    enrollment_message,
    issue_challenge,
    load_public_key,
    record_audit,
    record_device_event,
    revoke_sessions,
    verify_signature,
)
from devices.serializers import (
    DeviceAuthenticationSerializer,
    DeviceReasonSerializer,
    EnrollmentSerializer,
)
from staff.models import StaffProfile

from .auth_views import token_response


def staff_profile_for(user):
    if user.role != user.Role.STAFF:
        raise PermissionDenied("Staff device access is required.")
    try:
        return StaffProfile.objects.get(user=user, school=user.school)
    except StaffProfile.DoesNotExist as error:
        raise PermissionDenied("Staff device access is required.") from error


def device_data(device, include_history=False):
    data = {
        "id": str(device.pk),
        "staff_id": str(device.staff_profile_id),
        "employee_number": device.staff_profile.employee_number,
        "staff_name": (
            f"{device.staff_profile.first_name} {device.staff_profile.last_name}".strip()
        ),
        "platform": device.platform,
        "device_name": device.device_name,
        "status": device.status,
        "enrolled_at": device.enrolled_at.isoformat(),
        "created_at": device.created_at.isoformat(),
        "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "keys": [
            {
                "algorithm": key.algorithm,
                "fingerprint": key.fingerprint,
                "key_version": key.key_version,
                "status": key.status,
                "created_at": key.created_at.isoformat(),
                "retired_at": key.retired_at.isoformat() if key.retired_at else None,
            }
            for key in device.keys.all()
        ],
    }
    if include_history:
        events = [
            {
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat(),
                "metadata": event.metadata,
            }
            for event in device.events.all()
        ]
        audit_events = [
            {
                "action": event.action,
                "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
                "created_at": event.created_at.isoformat(),
                "after_data": event.after_data or {},
            }
            for event in (
                AuditLog.objects.filter(school=device.school)
                .filter(
                    Q(entity_type="RegisteredDevice", entity_id=device.pk)
                    | Q(
                        entity_type="UserSession",
                        after_data__device_id=str(device.pk),
                    )
                )
                .order_by("created_at")
            )
        ]
        data["history"] = events
        data["audit_history"] = audit_events
    return data


def enrollment_rejected(user, entity_id, reason):
    record_audit(
        school=user.school,
        actor=user,
        action="DEVICE_ENROLLMENT_REJECTED",
        entity_type="AuthenticationChallenge" if entity_id else "User",
        entity_id=entity_id or user.pk,
        after_data={"reason_code": reason},
    )
    return Response(
        {
            "state": "ENROLLMENT_REJECTED",
            "detail": "Device enrollment could not be completed.",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


class EnrollmentChallengeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        profile = staff_profile_for(request.user)
        challenge_value, challenge = issue_challenge(
            request.user, ENROLLMENT_PURPOSE
        )
        return Response(
            {
                "challenge": challenge_value,
                "expires_at": challenge.expires_at.isoformat(),
                "algorithm": SIGNATURE_ALGORITHM,
                "signature_message": enrollment_message(
                    challenge_value, request.user, request.user.school
                ).decode("utf-8"),
                "staff_id": str(profile.pk),
                "school_id": str(request.user.school_id),
            },
            status=status.HTTP_201_CREATED,
        )


class DeviceEnrollmentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        profile = staff_profile_for(request.user)
        serializer = EnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        with transaction.atomic():
            profile = StaffProfile.objects.select_for_update().get(pk=profile.pk)
            challenge = (
                AuthenticationChallenge.objects.select_for_update()
                .filter(
                    challenge_hash=digest(values["challenge"]),
                    purpose=ENROLLMENT_PURPOSE,
                    user=request.user,
                    school=request.user.school,
                )
                .first()
            )
            if (
                challenge is None
                or challenge.consumed_at is not None
                or challenge.expires_at <= timezone.now()
            ):
                return enrollment_rejected(
                    request.user,
                    challenge.pk if challenge else None,
                    "challenge_invalid",
                )

            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at", "updated_at"])
            try:
                public_key, public_key_pem, fingerprint = load_public_key(
                    values["public_key"]
                )
                verify_signature(
                    public_key,
                    values["signature"],
                    enrollment_message(
                        values["challenge"], request.user, request.user.school
                    ),
                )
            except DeviceProtocolError:
                return enrollment_rejected(
                    request.user, challenge.pk, "signature_or_key_invalid"
                )

            if RegisteredDevice.objects.filter(
                staff_profile=profile, status=RegisteredDevice.Status.ACTIVE
            ).exists():
                record_audit(
                    school=request.user.school,
                    actor=request.user,
                    action="DEVICE_ENROLLMENT_REJECTED",
                    entity_type="AuthenticationChallenge",
                    entity_id=challenge.pk,
                    after_data={"reason_code": "active_device_exists"},
                )
                return Response(
                    {
                        "state": "DEVICE_ALREADY_ACTIVE",
                        "detail": "An active device is already registered.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            if DeviceKey.objects.filter(fingerprint=fingerprint).exists():
                return enrollment_rejected(
                    request.user, challenge.pk, "public_key_already_registered"
                )

            now = timezone.now()
            device = RegisteredDevice.objects.create(
                school=profile.school,
                staff_profile=profile,
                platform=values["platform"],
                device_name=values["device_name"],
                status=RegisteredDevice.Status.PENDING,
                enrolled_at=now,
            )
            DeviceKey.objects.create(
                school=profile.school,
                device=device,
                public_key=public_key_pem,
                algorithm=SIGNATURE_ALGORITHM,
                fingerprint=fingerprint,
                key_version=1,
                status=DeviceKey.Status.ACTIVE,
            )
            record_device_event(
                device,
                DeviceEvent.EventType.ENROLLMENT,
                request.user,
                "DEVICE_ENROLLMENT_SUCCEEDED",
                {"status": device.status, "key_fingerprint": fingerprint},
            )

        return Response(
            {
                "device": device_data(device),
                "state": "PENDING",
                "detail": "Device enrollment is waiting for school administrator approval.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DeviceAuthenticationChallengeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        profile = staff_profile_for(request.user)
        device = (
            RegisteredDevice.objects.filter(
                staff_profile=profile, status=RegisteredDevice.Status.ACTIVE
            )
            .order_by("-created_at")
            .first()
        )
        if device is None or not device_has_active_key(device):
            return Response(
                {
                    "state": "DEVICE_NOT_ACTIVE",
                    "detail": "No active trusted device is available.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        challenge_value, challenge = issue_challenge(
            request.user, DEVICE_AUTHENTICATION_PURPOSE, device=device
        )
        return Response(
            {
                "challenge": challenge_value,
                "device_id": str(device.pk),
                "expires_at": challenge.expires_at.isoformat(),
                "algorithm": SIGNATURE_ALGORITHM,
                "signature_message": device_authentication_message(
                    challenge_value, request.user, device
                ).decode("utf-8"),
                "school_id": str(request.user.school_id),
            },
            status=status.HTTP_201_CREATED,
        )


class DeviceSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        profile = staff_profile_for(request.user)
        serializer = DeviceAuthenticationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        with transaction.atomic():
            StaffProfile.objects.select_for_update().get(pk=profile.pk)
            challenge = (
                AuthenticationChallenge.objects.select_for_update()
                .filter(
                    challenge_hash=digest(values["challenge"]),
                    purpose=DEVICE_AUTHENTICATION_PURPOSE,
                    user=request.user,
                    school=request.user.school,
                )
                .first()
            )
            if (
                challenge is None
                or challenge.consumed_at is not None
                or challenge.expires_at <= timezone.now()
                or challenge.device_id is None
            ):
                return Response(
                    {
                        "state": "DEVICE_AUTHENTICATION_REJECTED",
                        "detail": "Device authentication could not be completed.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            device = RegisteredDevice.objects.select_for_update().get(
                pk=challenge.device_id, school=request.user.school
            )
            if device.status != RegisteredDevice.Status.ACTIVE:
                return Response(
                    {
                        "state": "DEVICE_AUTHENTICATION_REJECTED",
                        "detail": "Device authentication could not be completed.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            key = DeviceKey.objects.filter(
                device=device, status=DeviceKey.Status.ACTIVE
            ).first()
            if key is None or key.algorithm != SIGNATURE_ALGORITHM:
                return Response(
                    {
                        "state": "DEVICE_AUTHENTICATION_REJECTED",
                        "detail": "Device authentication could not be completed.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at", "updated_at"])
            try:
                public_key, _, fingerprint = load_public_key(key.public_key)
                if fingerprint != key.fingerprint:
                    raise DeviceProtocolError("Device key fingerprint mismatch.")
                verify_signature(
                    public_key,
                    values["signature"],
                    device_authentication_message(
                        values["challenge"], request.user, device
                    ),
                )
            except DeviceProtocolError:
                record_audit(
                    school=request.user.school,
                    actor=request.user,
                    action="DEVICE_AUTHENTICATION_REJECTED",
                    entity_type="AuthenticationChallenge",
                    entity_id=challenge.pk,
                    after_data={"reason_code": "signature_invalid"},
                )
                return Response(
                    {
                        "state": "DEVICE_AUTHENTICATION_REJECTED",
                        "detail": "Device authentication could not be completed.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if request.auth.device_id is None:
                revoke_sessions(
                    UserSession.objects.filter(pk=request.auth.pk),
                    actor=request.user,
                    reason="device_session_established",
                )
            device.last_seen_at = timezone.now()
            device.save(update_fields=["last_seen_at", "updated_at"])
            session, refresh_token = create_session(
                request.user, device=device
            )

        return Response(token_response(session, refresh_token))


class DeviceListView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get(self, request, version):
        devices = (
            RegisteredDevice.objects.filter(school=request.user.school)
            .select_related("staff_profile")
            .prefetch_related("keys")
        )
        return Response([device_data(device) for device in devices])


def admin_device_queryset(request):
    return (
        RegisteredDevice.objects.filter(school=request.user.school)
        .select_related("staff_profile")
        .prefetch_related("keys")
    )


class DeviceDetailView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get(self, request, version, device_id):
        device = get_object_or_404(admin_device_queryset(request), pk=device_id)
        return Response(device_data(device, include_history=True))


class DeviceDecisionView(APIView):
    permission_classes = [IsSchoolAdmin]
    target_status = None

    def post(self, request, version, device_id):
        reason = ""
        if self.target_status != RegisteredDevice.Status.ACTIVE:
            serializer = DeviceReasonSerializer(data=request.data or {})
            serializer.is_valid(raise_exception=True)
            reason = serializer.validated_data.get("reason", "")
        elif request.data:
            raise serializers.ValidationError(
                {"detail": "The request contains unsupported fields."}
            )

        queryset = admin_device_queryset(request)
        try:
            with transaction.atomic():
                candidate = get_object_or_404(queryset, pk=device_id)
                StaffProfile.objects.select_for_update().get(
                    pk=candidate.staff_profile_id
                )
                device = get_object_or_404(
                    queryset.select_for_update(), pk=device_id
                )
                now = timezone.now()

                if self.target_status == RegisteredDevice.Status.ACTIVE:
                    if device.status != RegisteredDevice.Status.PENDING:
                        return Response(
                            {"detail": "Only pending devices can be approved."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    if RegisteredDevice.objects.filter(
                        staff_profile=device.staff_profile,
                        status=RegisteredDevice.Status.ACTIVE,
                    ).exists():
                        return Response(
                            {
                                "detail": "The staff member already has an active device."
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                    device.status = RegisteredDevice.Status.ACTIVE
                    device.save(update_fields=["status", "updated_at"])
                    record_device_event(
                        device,
                        DeviceEvent.EventType.APPROVAL,
                        request.user,
                        "DEVICE_APPROVED",
                        {"status": device.status},
                    )
                elif self.target_status == RegisteredDevice.Status.REJECTED:
                    if device.status != RegisteredDevice.Status.PENDING:
                        return Response(
                            {"detail": "Only pending devices can be rejected."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    device.status = RegisteredDevice.Status.REJECTED
                    device.save(update_fields=["status", "updated_at"])
                    DeviceKey.objects.filter(device=device).update(
                        status=DeviceKey.Status.REVOKED, retired_at=now
                    )
                    record_device_event(
                        device,
                        DeviceEvent.EventType.REJECTION,
                        request.user,
                        "DEVICE_REJECTED",
                        {"status": device.status, "reason": reason},
                    )
                else:
                    if device.status != RegisteredDevice.Status.ACTIVE:
                        return Response(
                            {"detail": "Only active devices can be revoked."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    device.status = RegisteredDevice.Status.REVOKED
                    device.revoked_at = now
                    device.save(
                        update_fields=["status", "revoked_at", "updated_at"]
                    )
                    DeviceKey.objects.filter(
                        device=device, status=DeviceKey.Status.ACTIVE
                    ).update(status=DeviceKey.Status.REVOKED, retired_at=now)
                    revoke_sessions(
                        UserSession.objects.filter(device=device),
                        actor=request.user,
                        reason="device_revoked",
                    )
                    record_device_event(
                        device,
                        DeviceEvent.EventType.REVOCATION,
                        request.user,
                        "DEVICE_REVOKED",
                        {"status": device.status, "reason": reason},
                    )
        except IntegrityError:
            return Response(
                {"detail": "The staff member already has an active device."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(device_data(device, include_history=True))


class DeviceApproveView(DeviceDecisionView):
    target_status = RegisteredDevice.Status.ACTIVE


class DeviceRejectView(DeviceDecisionView):
    target_status = RegisteredDevice.Status.REJECTED


class DeviceRevokeView(DeviceDecisionView):
    target_status = RegisteredDevice.Status.REVOKED
