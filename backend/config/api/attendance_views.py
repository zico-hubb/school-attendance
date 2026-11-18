from datetime import datetime, time
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    IsAuthenticated,
    IsSchoolAdmin,
    IsSchoolAdminOrAttendanceManager,
)
from attendance.models import (
    AttendanceAttempt,
    AttendanceEvent,
    AttendanceRecord,
    AttendanceRecordHistory,
)
from devices.models import (
    AuthenticationChallenge,
    DeviceKey,
    RegisteredDevice,
)
from devices.services import (
    ATTENDANCE_CHECK_IN_PURPOSE,
    ATTENDANCE_CHECK_OUT_PURPOSE,
    SIGNATURE_ALGORITHM,
    DeviceProtocolError,
    digest,
    device_attendance_message,
    device_session_is_usable,
    issue_challenge,
    load_public_key,
    record_audit,
    verify_signature,
)
from leave_management.models import LeaveRecord
from locations.models import AttendanceZone, ApprovedAccessPoint
from scheduling.services import schedule_for_date
from staff.models import StaffProfile


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class AttendanceChallengeSerializer(StrictSerializer):
    attempt_type = serializers.ChoiceField(choices=("CHECK_IN", "CHECK_OUT"))


class AttendanceSubmissionSerializer(StrictSerializer):
    challenge = serializers.CharField(max_length=128)
    signature = serializers.CharField(max_length=256)
    attempt_type = serializers.ChoiceField(choices=("CHECK_IN", "CHECK_OUT"))
    idempotency_key = serializers.CharField(max_length=128)
    evidence_timestamp = serializers.DateTimeField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    location_accuracy = serializers.DecimalField(max_digits=8, decimal_places=2)
    bssid = serializers.CharField(max_length=64, required=False, allow_blank=True)


def get_staff_profile(request):
    if request.user.role != request.user.Role.STAFF:
        raise PermissionDenied("Staff attendance access is required.")
    try:
        return StaffProfile.objects.select_related("department", "user").get(
            school=request.user.school, user=request.user
        )
    except StaffProfile.DoesNotExist as error:
        raise PermissionDenied("Staff attendance access is required.") from error


def get_device(request):
    session = request.auth
    if session.device_id is None or not device_session_is_usable(session):
        raise PermissionDenied("An approved device-bound session is required.")
    device = RegisteredDevice.objects.select_related("staff_profile").get(
        pk=session.device_id,
        school=request.user.school,
        staff_profile__user=request.user,
        status=RegisteredDevice.Status.ACTIVE,
    )
    return device


class AttendanceChallengeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        profile = get_staff_profile(request)
        serializer = AttendanceChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = get_device(request)
        purpose = (
            ATTENDANCE_CHECK_IN_PURPOSE
            if serializer.validated_data["attempt_type"] == "CHECK_IN"
            else ATTENDANCE_CHECK_OUT_PURPOSE
        )
        challenge_value, challenge = issue_challenge(
            request.user, purpose, device=device
        )
        return Response(
            {
                "challenge": challenge_value,
                "expires_at": challenge.expires_at.isoformat(),
                "algorithm": SIGNATURE_ALGORITHM,
                "signature_message": device_attendance_message(
                    challenge_value,
                    request.user,
                    device,
                    serializer.validated_data["attempt_type"],
                ).decode("utf-8"),
                "device_id": str(device.pk),
                "staff_id": str(profile.pk),
                "school_id": str(request.user.school_id),
            },
            status=status.HTTP_201_CREATED,
        )


def distance_meters(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def evidence_for_request(request, profile, evidence_timestamp, latitude, longitude,
                         location_accuracy, bssid):
    now = timezone.now()
    age_seconds = abs((now - evidence_timestamp).total_seconds())
    if age_seconds > settings.ATTENDANCE_LOCATION_MAX_AGE_SECONDS:
        return "EVIDENCE_TOO_OLD", "Location evidence is too old."
    if location_accuracy > Decimal(str(settings.ATTENDANCE_LOCATION_MAX_ACCURACY_METERS)):
        return "LOCATION_ACCURACY_INSUFFICIENT", "Location accuracy is insufficient."

    lat = float(latitude)
    lon = float(longitude)
    zone_match = None
    zones = AttendanceZone.objects.filter(
        school=profile.school, is_active=True
    )
    for zone in zones:
        distance = distance_meters(
            lat, lon, float(zone.latitude), float(zone.longitude)
        )
        effective_radius = float(zone.radius_meters) + float(location_accuracy)
        if distance <= effective_radius:
            zone_match = zone
            break
    if zone_match is None:
        return "OUTSIDE_ATTENDANCE_ZONE", "Location is outside an approved attendance zone."

    bssid_match = False
    if bssid:
        compact = bssid.upper().replace(":", "").replace("-", "").replace(".", "")
        if len(compact) == 12:
            normalized = ":".join(compact[index:index + 2] for index in range(0, 12, 2))
            bssid_match = ApprovedAccessPoint.objects.filter(
                school=profile.school,
                attendance_zone=zone_match,
                is_active=True,
                normalized_bssid=normalized,
            ).exists()
    return "LOCATION_VERIFIED", "Evidence accepted; GPS and zone policy passed."


def local_attendance_date(profile, timestamp):
    try:
        zone = ZoneInfo(profile.school.timezone)
    except Exception:
        zone = ZoneInfo(settings.TIME_ZONE)
    local = timestamp.astimezone(zone)
    return local.date(), local


def approved_leave(profile, target_date):
    return LeaveRecord.objects.filter(
        school=profile.school,
        staff_profile=profile,
        status=LeaveRecord.Status.APPROVED,
        start_date__lte=target_date,
        end_date__gte=target_date,
    ).select_related("leave_type").first()


def classify_record(profile, target_date, check_in=None, check_out=None):
    schedule = schedule_for_date(profile, target_date)
    leave = approved_leave(profile, target_date)
    zone = None
    try:
        zone = ZoneInfo(profile.school.timezone)
    except Exception:
        zone = ZoneInfo(settings.TIME_ZONE)
    now = timezone.now().astimezone(zone)
    if leave is not None:
        status_value = AttendanceRecord.Status.ON_LEAVE
    elif schedule is None or not schedule["is_working_day"]:
        status_value = None
    elif check_in is None:
        deadline = schedule["absence_finalization_time"]
        if deadline is not None:
            deadline_dt = timezone.datetime.combine(target_date, deadline, tzinfo=zone)
            status_value = (
                AttendanceRecord.Status.ABSENT
                if now >= deadline_dt
                else AttendanceRecord.Status.NOT_YET_CHECKED_IN
            )
        else:
            status_value = AttendanceRecord.Status.NOT_YET_CHECKED_IN
    elif check_out is None:
        end_time = schedule["end_time"]
        if end_time is not None:
            end_dt = timezone.datetime.combine(target_date, end_time, tzinfo=zone)
            status_value = (
                AttendanceRecord.Status.INCOMPLETE
                if now >= end_dt
                else AttendanceRecord.Status.NOT_YET_CHECKED_IN
            )
        else:
            status_value = AttendanceRecord.Status.NOT_YET_CHECKED_IN
    else:
        status_value = AttendanceRecord.Status.PRESENT
        if schedule["late_after"] is not None:
            late_time = schedule["late_after"]
            late_boundary = timezone.datetime.combine(
                target_date, late_time, tzinfo=zone
            )
            actual = check_in.occurred_at.astimezone(zone)
            if actual > late_boundary:
                status_value = AttendanceRecord.Status.LATE

    return status_value, schedule, leave


def upsert_attendance_record(profile, target_date):
    check_in = AttendanceEvent.objects.filter(
        school=profile.school,
        staff_profile=profile,
        attendance_date=target_date,
        event_type=AttendanceEvent.EventType.CHECK_IN,
    ).first()
    check_out = AttendanceEvent.objects.filter(
        school=profile.school,
        staff_profile=profile,
        attendance_date=target_date,
        event_type=AttendanceEvent.EventType.CHECK_OUT,
    ).first()

    status_value, schedule, leave = classify_record(
        profile, target_date, check_in, check_out
    )
    if status_value is None:
        return None

    minutes_late = 0
    if status_value == AttendanceRecord.Status.LATE and check_in is not None and schedule and schedule["late_after"]:
        try:
            zone = ZoneInfo(profile.school.timezone)
        except Exception:
            zone = ZoneInfo(settings.TIME_ZONE)
        late_boundary = timezone.datetime.combine(
            target_date, schedule["late_after"], tzinfo=zone
        )
        actual = check_in.occurred_at.astimezone(zone)
        minutes_late = max(0, int((actual - late_boundary).total_seconds() // 60))

    values = {
        "status": status_value,
        "minutes_late": minutes_late,
        "check_in_event": check_in,
        "check_out_event": check_out,
        "schedule_version": schedule["version"] if schedule and schedule.get("version") else None,
        "schedule_assignment": schedule["assignment"] if schedule and schedule.get("assignment") else None,
        "leave_record": leave,
        "calculated_at": timezone.now(),
    }
    record = AttendanceRecord.objects.filter(
        school=profile.school,
        staff_profile=profile,
        attendance_date=target_date,
    ).select_for_update().first()
    if record is None:
        record = AttendanceRecord.objects.create(
            school=profile.school,
            staff_profile=profile,
            attendance_date=target_date,
            **values,
        )
    else:
        previous_status = record.status
        previous_values = {
            "check_in_event": str(record.check_in_event_id) if record.check_in_event_id else None,
            "check_out_event": str(record.check_out_event_id) if record.check_out_event_id else None,
            "status": record.status,
        }
        for key, value in values.items():
            setattr(record, key, value)
        record.save()
        if previous_status != record.status:
            AttendanceRecordHistory.objects.create(
                school=profile.school,
                attendance_record=record,
                previous_status=previous_status,
                new_status=record.status,
                previous_values=previous_values,
                new_values={"status": record.status},
                recalculation_reason="Attendance event accepted",
            )
    return record


class AttendanceSubmissionView(APIView):
    permission_classes = [IsAuthenticated]
    attempt_type = None

    def post(self, request, version):
        profile = get_staff_profile(request)
        device = get_device(request)
        serializer = AttendanceSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values["attempt_type"] != self.attempt_type:
            return Response(
                {"detail": "The submission attempt type does not match this endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        evidence_timestamp = values["evidence_timestamp"]
        attendance_date, _ = local_attendance_date(profile, evidence_timestamp)
        if timezone.is_naive(evidence_timestamp):
            evidence_timestamp = timezone.make_aware(evidence_timestamp)

        existing = AttendanceAttempt.objects.filter(
            device=device, idempotency_key=values["idempotency_key"]
        ).first()
        if existing:
            event = getattr(existing, "attendance_event", None)
            if existing.verification_result == AttendanceAttempt.VerificationResult.ACCEPTED and event:
                record = upsert_attendance_record(profile, existing.attendance_date)
                return Response(
                    {
                        "state": "IDEMPOTENT_ACCEPTED",
                        "attempt_id": str(existing.pk),
                        "event_id": str(event.pk),
                        "attendance_date": str(existing.attendance_date),
                        "status": record.status if record else None,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "state": "IDEMPOTENT_REJECTED",
                    "attempt_id": str(existing.pk),
                    "reason_code": existing.rejection_reason,
                },
                status=status.HTTP_409_CONFLICT,
            )

        duplicate = AttendanceEvent.objects.filter(
            school=request.user.school,
            staff_profile=profile,
            attendance_date=attendance_date,
            event_type=self.attempt_type,
        ).exists()
        if duplicate:
            return Response(
                {
                    "state": "REJECTED",
                    "reason_code": (
                        "DUPLICATE_CHECK_IN"
                        if self.attempt_type == "CHECK_IN"
                        else "DUPLICATE_CHECK_OUT"
                    ),
                    "detail": "An accepted event of this type already exists for the date.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        reason_code = ""
        detail = ""
        with transaction.atomic():
            purpose = (
                ATTENDANCE_CHECK_IN_PURPOSE
                if self.attempt_type == "CHECK_IN"
                else ATTENDANCE_CHECK_OUT_PURPOSE
            )
            challenge = (
                AuthenticationChallenge.objects.select_for_update()
                .filter(
                    challenge_hash=digest(values["challenge"]),
                    purpose=purpose,
                    user=request.user,
                    device=device,
                    school=request.user.school,
                )
                .first()
            )
            if (
                challenge is None
                or challenge.consumed_at is not None
                or challenge.expires_at <= timezone.now()
            ):
                reason_code, detail = "CHALLENGE_INVALID", "Challenge is invalid, expired, or already used."
                challenge_id = challenge.pk if challenge else None
            else:
                key = DeviceKey.objects.filter(
                    device=device,
                    status=DeviceKey.Status.ACTIVE,
                    algorithm=SIGNATURE_ALGORITHM,
                ).first()
                if key is None:
                    reason_code, detail = "DEVICE_NOT_ACTIVE", "The active device key is unavailable."
                    challenge_id = challenge.pk
                else:
                    try:
                        public_key, _, fingerprint = load_public_key(key.public_key)
                        if fingerprint != key.fingerprint:
                            raise DeviceProtocolError("Key mismatch.")
                        verify_signature(
                            public_key,
                            values["signature"],
                            device_attendance_message(
                                values["challenge"],
                                request.user,
                                device,
                                self.attempt_type,
                            ),
                        )
                    except DeviceProtocolError:
                        reason_code, detail = "SIGNATURE_INVALID", "The attendance signature is invalid."
                        challenge_id = challenge.pk
                    else:
                        challenge.consumed_at = timezone.now()
                        challenge.save(update_fields=["consumed_at", "updated_at"])
                        reason_code, detail = evidence_for_request(
                            request,
                            profile,
                            evidence_timestamp,
                            values["latitude"],
                            values["longitude"],
                            values["location_accuracy"],
                            values.get("bssid", ""),
                        )
                        challenge_id = challenge.pk

            accepted = reason_code in {"LOCATION_VERIFIED", ""}
            attempt = AttendanceAttempt.objects.create(
                school=request.user.school,
                staff_profile=profile,
                device=device,
                challenge_id=challenge_id,
                attempt_type=self.attempt_type,
                attendance_date=attendance_date,
                client_occurred_at=evidence_timestamp,
                latitude=values["latitude"],
                longitude=values["longitude"],
                location_accuracy=values["location_accuracy"],
                bssid=values.get("bssid", ""),
                public_ip=request.META.get("REMOTE_ADDR"),
                idempotency_key=values["idempotency_key"],
                verification_result=(
                    AttendanceAttempt.VerificationResult.ACCEPTED
                    if accepted
                    else AttendanceAttempt.VerificationResult.REJECTED
                ),
                rejection_reason="" if accepted else reason_code,
                verification_details={
                    "reason_code": reason_code,
                    "detail": detail,
                    "bssid_supplied": bool(values.get("bssid")),
                    "server_received_at": timezone.now().isoformat(),
                },
            )

            if not accepted:
                record_audit(
                    school=request.user.school,
                    actor=request.user,
                    action="ATTENDANCE_ATTEMPT_REJECTED",
                    entity_type="AttendanceAttempt",
                    entity_id=attempt.pk,
                    after_data={"reason_code": reason_code, "attempt_type": self.attempt_type},
                )
                return Response(
                    {
                        "state": "REJECTED",
                        "attempt_id": str(attempt.pk),
                        "reason_code": reason_code,
                        "detail": detail,
                    },
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            if self.attempt_type == "CHECK_OUT":
                check_in = AttendanceEvent.objects.filter(
                    school=request.user.school,
                    staff_profile=profile,
                    attendance_date=attendance_date,
                    event_type=AttendanceEvent.EventType.CHECK_IN,
                ).exists()
                if not check_in:
                    attempt.verification_result = AttendanceAttempt.VerificationResult.REJECTED
                    attempt.rejection_reason = "CHECK_OUT_BEFORE_CHECK_IN"
                    attempt.verification_details["reason_code"] = "CHECK_OUT_BEFORE_CHECK_IN"
                    attempt.save(update_fields=["verification_result", "rejection_reason", "verification_details"])
                    return Response(
                        {
                            "state": "REJECTED",
                            "attempt_id": str(attempt.pk),
                            "reason_code": "CHECK_OUT_BEFORE_CHECK_IN",
                            "detail": "A check-out requires an accepted check-in.",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            profile_row = StaffProfile.objects.select_for_update().get(pk=profile.pk)
            event = AttendanceEvent.objects.create(
                school=request.user.school,
                staff_profile=profile_row,
                device=device,
                attendance_attempt=attempt,
                attendance_date=attendance_date,
                event_type=self.attempt_type,
            )
            record_audit(
                school=request.user.school,
                actor=request.user,
                action="ATTENDANCE_EVENT_ACCEPTED",
                entity_type="AttendanceEvent",
                entity_id=event.pk,
                after_data={"attempt_type": self.attempt_type, "attendance_date": str(attendance_date)},
            )
            record = upsert_attendance_record(profile_row, attendance_date)

        return Response(
            {
                "state": "ACCEPTED",
                "attempt_id": str(attempt.pk),
                "event_id": str(event.pk),
                "attendance_date": str(attendance_date),
                "status": record.status if record else None,
            },
            status=status.HTTP_201_CREATED,
        )


class AttendanceCheckInView(AttendanceSubmissionView):
    attempt_type = "CHECK_IN"


class AttendanceCheckOutView(AttendanceSubmissionView):
    attempt_type = "CHECK_OUT"


class AttendanceStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, version):
        profile = get_staff_profile(request)
        attendance_date, _ = local_attendance_date(profile, timezone.now())
        record = upsert_attendance_record(profile, attendance_date)
        schedule = schedule_for_date(profile, attendance_date)
        leave = approved_leave(profile, attendance_date)
        events = AttendanceEvent.objects.filter(
            school=request.user.school,
            staff_profile=profile,
            attendance_date=attendance_date,
        )
        return Response(
            {
                "attendance_date": str(attendance_date),
                "status": record.status if record else None,
                "schedule": {
                    "source": schedule["source"] if schedule else None,
                    "is_working_day": schedule["is_working_day"] if schedule else None,
                    "start_time": schedule["start_time"].isoformat() if schedule and schedule["start_time"] else None,
                    "end_time": schedule["end_time"].isoformat() if schedule and schedule["end_time"] else None,
                    "late_after": schedule["late_after"].isoformat() if schedule and schedule["late_after"] else None,
                } if schedule else None,
                "leave": leave.status if leave else None,
                "checked_in": events.filter(event_type="CHECK_IN").exists(),
                "checked_out": events.filter(event_type="CHECK_OUT").exists(),
            }
        )


class AttendanceHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, version):
        profile = get_staff_profile(request)
        records = AttendanceRecord.objects.filter(
            school=request.user.school, staff_profile=profile
        ).order_by("-attendance_date")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            records = records.filter(attendance_date__gte=date_from)
        if date_to:
            records = records.filter(attendance_date__lte=date_to)
        return Response([
            {
                "attendance_date": str(record.attendance_date),
                "status": record.status,
                "check_in": record.check_in_event.occurred_at.isoformat() if record.check_in_event else None,
                "check_out": record.check_out_event.occurred_at.isoformat() if record.check_out_event else None,
                "minutes_late": record.minutes_late,
            }
            for record in records[:100]
        ])


class AttendanceRegisterView(APIView):
    permission_classes = [IsSchoolAdminOrAttendanceManager]

    def get(self, request, version):
        target_date = request.query_params.get("date")
        try:
            from datetime import date
            target_date = date.fromisoformat(target_date) if target_date else timezone.localdate()
        except ValueError:
            raise serializers.ValidationError({"date": "Use an ISO date in YYYY-MM-DD format."})

        records = AttendanceRecord.objects.filter(
            school=request.user.school, attendance_date=target_date
        ).select_related("staff_profile", "staff_profile__department")
        if not records.exists():
            profiles = StaffProfile.objects.filter(
                school=request.user.school,
                employment_status=StaffProfile.EmploymentStatus.ACTIVE,
            )
            for profile in profiles:
                upsert_attendance_record(profile, target_date)
            records = AttendanceRecord.objects.filter(
                school=request.user.school, attendance_date=target_date
            ).select_related("staff_profile", "staff_profile__department")
        return Response([
            {
                "attendance_date": str(record.attendance_date),
                "staff_id": str(record.staff_profile_id),
                "employee_number": record.staff_profile.employee_number,
                "staff_name": f"{record.staff_profile.first_name} {record.staff_profile.last_name}".strip(),
                "department": record.staff_profile.department.name if record.staff_profile.department else None,
                "status": record.status,
                "check_in": record.check_in_event.occurred_at.isoformat() if record.check_in_event else None,
                "check_out": record.check_out_event.occurred_at.isoformat() if record.check_out_event else None,
            }
            for record in records
        ])
