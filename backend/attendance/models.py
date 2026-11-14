from django.core.exceptions import ValidationError
from django.db import models, transaction

from common.models import (
    AppendOnlyModel,
    SchoolOwnedModel,
    validate_same_school,
)


class AttendanceAttempt(AppendOnlyModel):
    class AttemptType(models.TextChoices):
        CHECK_IN = "CHECK_IN", "Check-in"
        CHECK_OUT = "CHECK_OUT", "Check-out"

    class VerificationResult(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    staff_profile = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="attendance_attempts"
    )
    device = models.ForeignKey(
        "devices.RegisteredDevice",
        on_delete=models.PROTECT,
        related_name="attendance_attempts",
    )
    challenge = models.ForeignKey(
        "devices.AuthenticationChallenge",
        on_delete=models.PROTECT,
        related_name="attendance_attempts",
        null=True,
        blank=True,
    )
    attempt_type = models.CharField(max_length=9, choices=AttemptType.choices)
    attendance_date = models.DateField()
    client_occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_accuracy = models.DecimalField(max_digits=8, decimal_places=2)
    bssid = models.CharField(max_length=64, blank=True)
    public_ip = models.GenericIPAddressField(null=True, blank=True)
    rssi = models.SmallIntegerField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128)
    verification_result = models.CharField(
        max_length=8,
        choices=VerificationResult.choices,
        default=VerificationResult.PENDING,
    )
    rejection_reason = models.CharField(max_length=160, blank=True)
    verification_details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "idempotency_key"],
                name="attendance_attempt_device_idempotency_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90) & models.Q(latitude__lte=90),
                name="attendance_attempt_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180)
                & models.Q(longitude__lte=180),
                name="attendance_attempt_longitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(location_accuracy__gte=0),
                name="attendance_attempt_accuracy_nonnegative",
            ),
        ]

    def clean(self):
        super().clean()
        related = [self.staff_profile, self.device]
        if self.challenge_id:
            related.append(self.challenge)
        validate_same_school(self, *related)
        if self.device_id and self.device.staff_profile_id != self.staff_profile_id:
            raise ValidationError({"device": "The device must belong to this staff member."})
        if self.challenge_id:
            if (
                self.challenge.user_id
                and self.challenge.user_id != self.staff_profile.user_id
            ):
                raise ValidationError({"challenge": "The challenge is bound to another user."})
            if self.challenge.device_id and self.challenge.device_id != self.device_id:
                raise ValidationError({"challenge": "The challenge is bound to another device."})


class AttendanceEvent(AppendOnlyModel):
    class EventType(models.TextChoices):
        CHECK_IN = "CHECK_IN", "Check-in"
        CHECK_OUT = "CHECK_OUT", "Check-out"

    staff_profile = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="attendance_events"
    )
    device = models.ForeignKey(
        "devices.RegisteredDevice",
        on_delete=models.PROTECT,
        related_name="attendance_events",
    )
    attendance_attempt = models.OneToOneField(
        AttendanceAttempt, on_delete=models.PROTECT, related_name="attendance_event"
    )
    attendance_date = models.DateField()
    event_type = models.CharField(max_length=9, choices=EventType.choices)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff_profile", "attendance_date"],
                condition=models.Q(event_type="CHECK_IN"),
                name="one_check_in_per_staff_day",
            ),
            models.UniqueConstraint(
                fields=["staff_profile", "attendance_date"],
                condition=models.Q(event_type="CHECK_OUT"),
                name="one_check_out_per_staff_day",
            ),
        ]

    def clean(self):
        super().clean()
        validate_same_school(
            self, self.staff_profile, self.device, self.attendance_attempt
        )
        if self.device.staff_profile_id != self.staff_profile_id:
            raise ValidationError({"device": "The device must belong to this staff member."})
        attempt = self.attendance_attempt
        if attempt.staff_profile_id != self.staff_profile_id:
            raise ValidationError(
                {"attendance_attempt": "The attempt must belong to this staff member."}
            )
        if attempt.device_id != self.device_id:
            raise ValidationError(
                {"attendance_attempt": "The attempt must use this device."}
            )
        if (
            attempt.attendance_date != self.attendance_date
            or attempt.attempt_type != self.event_type
        ):
            raise ValidationError(
                {"attendance_attempt": "The event must match the attempt date and type."}
            )
        if attempt.verification_result != AttendanceAttempt.VerificationResult.ACCEPTED:
            raise ValidationError(
                {"attendance_attempt": "Only accepted attempts can produce an event."}
            )
        if self.event_type == self.EventType.CHECK_OUT:
            check_in_exists = type(self).objects.filter(
                school_id=self.school_id,
                staff_profile_id=self.staff_profile_id,
                attendance_date=self.attendance_date,
                event_type=self.EventType.CHECK_IN,
            ).exists()
            if not check_in_exists:
                raise ValidationError(
                    {"event_type": "A check-out requires a preceding accepted check-in."}
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.staff_profile_id:
                type(self.staff_profile).objects.select_for_update().get(
                    pk=self.staff_profile_id
                )
            return super().save(*args, **kwargs)


class AttendanceRecord(SchoolOwnedModel):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        LATE = "LATE", "Late"
        ABSENT = "ABSENT", "Absent"
        ON_LEAVE = "ON_LEAVE", "On leave"
        NOT_YET_CHECKED_IN = "NOT_YET_CHECKED_IN", "Not yet checked in"
        INCOMPLETE = "INCOMPLETE", "Incomplete"

    staff_profile = models.ForeignKey(
        "staff.StaffProfile",
        on_delete=models.PROTECT,
        related_name="attendance_records",
    )
    attendance_date = models.DateField()
    check_in_event = models.OneToOneField(
        AttendanceEvent,
        on_delete=models.PROTECT,
        related_name="check_in_record",
        null=True,
        blank=True,
    )
    check_out_event = models.OneToOneField(
        AttendanceEvent,
        on_delete=models.PROTECT,
        related_name="check_out_record",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=24, choices=Status.choices)
    minutes_late = models.PositiveIntegerField(default=0)
    schedule_version = models.ForeignKey(
        "scheduling.ScheduleVersion",
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    schedule_assignment = models.ForeignKey(
        "scheduling.ScheduleAssignment",
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    leave_record = models.ForeignKey(
        "leave_management.LeaveRecord",
        on_delete=models.PROTECT,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    classification_version = models.PositiveIntegerField(default=1)
    calculated_at = models.DateTimeField()

    class Meta:
        ordering = ["-attendance_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff_profile", "attendance_date"],
                name="attendance_record_staff_date_uniq",
            )
        ]

    def clean(self):
        super().clean()
        related = [self.staff_profile]
        related.extend(
            value
            for value in [
                self.check_in_event if self.check_in_event_id else None,
                self.check_out_event if self.check_out_event_id else None,
                self.schedule_version if self.schedule_version_id else None,
                self.schedule_assignment if self.schedule_assignment_id else None,
                self.leave_record if self.leave_record_id else None,
            ]
            if value is not None
        )
        validate_same_school(self, *related)
        for event in (self.check_in_event, self.check_out_event):
            if event is not None and (
                event.staff_profile_id != self.staff_profile_id
                or event.attendance_date != self.attendance_date
            ):
                raise ValidationError(
                    "Attendance events must match the record's staff member and date."
                )
        if (
            self.check_in_event_id
            and self.check_in_event.event_type != AttendanceEvent.EventType.CHECK_IN
        ):
            raise ValidationError({"check_in_event": "Expected a CHECK_IN event."})
        if (
            self.check_out_event_id
            and self.check_out_event.event_type != AttendanceEvent.EventType.CHECK_OUT
        ):
            raise ValidationError({"check_out_event": "Expected a CHECK_OUT event."})


class AttendanceRecordHistory(AppendOnlyModel):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        LATE = "LATE", "Late"
        ABSENT = "ABSENT", "Absent"
        ON_LEAVE = "ON_LEAVE", "On leave"
        NOT_YET_CHECKED_IN = "NOT_YET_CHECKED_IN", "Not yet checked in"
        INCOMPLETE = "INCOMPLETE", "Incomplete"

    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="history"
    )
    previous_status = models.CharField(
        max_length=24, choices=Status.choices, null=True, blank=True
    )
    new_status = models.CharField(max_length=24, choices=Status.choices)
    previous_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict)
    recalculation_reason = models.CharField(max_length=160)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        super().clean()
        if self.attendance_record_id:
            validate_same_school(self, self.attendance_record)
