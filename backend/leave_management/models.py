from django.core.exceptions import ValidationError
from django.db import models, transaction

from common.models import SchoolOwnedModel, validate_date_range, validate_same_school
from schools.models import School


class SchoolCalendarEvent(SchoolOwnedModel):
    class EventType(models.TextChoices):
        HOLIDAY = "HOLIDAY", "Holiday"
        CLOSURE = "CLOSURE", "Closure"
        EXCEPTIONAL_WORKING_DAY = (
            "EXCEPTIONAL_WORKING_DAY",
            "Exceptional working day",
        )

    name = models.CharField(max_length=160)
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    late_after = models.TimeField(null=True, blank=True)
    absence_finalization_time = models.TimeField(null=True, blank=True)
    department = models.ForeignKey(
        "schools.Department",
        on_delete=models.PROTECT,
        related_name="calendar_events",
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_calendar_events",
    )

    class Meta:
        ordering = ["start_date", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="calendar_event_end_on_or_after_start",
            )
        ]

    def clean(self):
        super().clean()
        validate_date_range(self.start_date, self.end_date, "end_date")
        if self.department_id:
            validate_same_school(self, self.department)
        if self.created_by_id and self.created_by.school_id != self.school_id:
            raise ValidationError({"created_by": "The creator must belong to this school."})
        event_times = (
            self.start_time,
            self.end_time,
            self.late_after,
            self.absence_finalization_time,
        )
        if self.event_type == self.EventType.EXCEPTIONAL_WORKING_DAY:
            if any(value is None for value in event_times):
                raise ValidationError(
                    "Exceptional working days require start, end, late, and absence times."
                )
            if self.end_time <= self.start_time:
                raise ValidationError(
                    {"end_time": "End time must be after start time."}
                )
        elif any(value is not None for value in event_times):
            raise ValidationError(
                "Only exceptional working days can define attendance times."
            )
        if self.school_id and self.start_date and self.end_date:
            overlap = type(self).objects.filter(
                school_id=self.school_id,
                department_id=self.department_id,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError(
                    {"start_date": "Calendar events for this scope cannot overlap."}
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.school_id:
                School.objects.select_for_update().get(pk=self.school_id)
            return super().save(*args, **kwargs)


class LeaveType(SchoolOwnedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="leave_type_school_name_uniq"
            )
        ]


class LeaveRecord(SchoolOwnedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    staff_profile = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="leave_records"
    )
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.PROTECT, related_name="leave_records"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="reviewed_leave_records",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="cancelled_leave_records",
        null=True,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="leave_record_end_on_or_after_start",
            )
        ]

    def clean(self):
        super().clean()
        validate_date_range(self.start_date, self.end_date, "end_date")
        related = [self.staff_profile, self.leave_type]
        if self.reviewed_by_id:
            related.append(self.reviewed_by)
        if self.cancelled_by_id:
            related.append(self.cancelled_by)
        validate_same_school(self, *related)
        if self.status in {self.Status.APPROVED, self.Status.REJECTED} and (
            not self.reviewed_by_id or not self.reviewed_at
        ):
            raise ValidationError(
                "Reviewed leave records require a reviewer and review time."
            )
        if self.status == self.Status.CANCELLED and (
            not self.cancelled_by_id or not self.cancelled_at
        ):
            raise ValidationError(
                "Cancelled leave records require a cancelling user and time."
            )
        if self.status != self.Status.CANCELLED and (
            self.cancelled_by_id or self.cancelled_at
        ):
            raise ValidationError(
                "Only cancelled leave records can have cancellation details."
            )
        if self.status == self.Status.APPROVED:
            overlap = type(self).objects.filter(
                school_id=self.school_id,
                staff_profile_id=self.staff_profile_id,
                status=self.Status.APPROVED,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError(
                    {"start_date": "Approved leave periods for a staff member cannot overlap."}
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.staff_profile_id:
                type(self.staff_profile).objects.select_for_update().get(
                    pk=self.staff_profile_id
                )
            return super().save(*args, **kwargs)
