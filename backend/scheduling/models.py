from datetime import date

from django.core.exceptions import ValidationError
from django.db import models, transaction

from common.models import (
    SchoolOwnedCreatedModel,
    SchoolOwnedModel,
    validate_date_range,
    validate_same_school,
)


class WorkSchedule(SchoolOwnedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="work_schedule_name_uniq"
            )
        ]


class ScheduleVersion(SchoolOwnedModel):
    work_schedule = models.ForeignKey(
        WorkSchedule, on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_schedule_versions",
    )
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["work_schedule_id", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_schedule", "version_number"],
                name="schedule_version_number_uniq",
            )
        ]

    def clean(self):
        super().clean()
        validate_date_range(self.effective_from, self.effective_to)
        if self.work_schedule_id:
            validate_same_school(self, self.work_schedule)
        if self.created_by_id and self.created_by.school_id != self.school_id:
            raise ValidationError({"created_by": "The creator must belong to this school."})
        if self.is_active:
            weekday_count = self.days.values("weekday").distinct().count()
            if weekday_count != 7:
                raise ValidationError(
                    {"is_active": "All seven weekdays must be defined before activation."}
                )
        if self.work_schedule_id and self.effective_from:
            overlap = type(self).objects.filter(
                work_schedule_id=self.work_schedule_id,
                effective_from__lte=self.effective_to or date.max,
            ).filter(
                models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=self.effective_from)
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError(
                    {"effective_from": "Schedule version date ranges cannot overlap."}
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.work_schedule_id:
                WorkSchedule.objects.select_for_update().get(pk=self.work_schedule_id)
            return super().save(*args, **kwargs)

    def activate(self):
        with transaction.atomic():
            WorkSchedule.objects.select_for_update().get(pk=self.work_schedule_id)
            if self.days.values("weekday").distinct().count() != 7:
                raise ValidationError(
                    "All seven weekdays must be defined before activation."
                )
            self.is_active = True
            self.save()


class ScheduleDay(SchoolOwnedCreatedModel):
    schedule_version = models.ForeignKey(
        ScheduleVersion, on_delete=models.PROTECT, related_name="days"
    )
    weekday = models.PositiveSmallIntegerField()
    is_working_day = models.BooleanField(default=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    late_after = models.TimeField(null=True, blank=True)
    absence_finalization_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0) & models.Q(weekday__lte=6),
                name="schedule_day_weekday_range",
            ),
            models.UniqueConstraint(
                fields=["schedule_version", "weekday"],
                name="schedule_version_weekday_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_time__isnull=True)
                    | models.Q(end_time__isnull=True)
                    | models.Q(end_time__gt=models.F("start_time"))
                ),
                name="schedule_day_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        if self.schedule_version_id:
            validate_same_school(self, self.schedule_version)


class ScheduleAssignment(SchoolOwnedModel):
    work_schedule = models.ForeignKey(
        WorkSchedule, on_delete=models.PROTECT, related_name="assignments"
    )
    department = models.ForeignKey(
        "schools.Department",
        on_delete=models.PROTECT,
        related_name="schedule_assignments",
        null=True,
        blank=True,
    )
    staff_profile = models.ForeignKey(
        "staff.StaffProfile",
        on_delete=models.PROTECT,
        related_name="schedule_assignments",
        null=True,
        blank=True,
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_schedule_assignments",
    )

    class Meta:
        ordering = ["-effective_from"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(department__isnull=False, staff_profile__isnull=True)
                    | models.Q(department__isnull=True, staff_profile__isnull=False)
                ),
                name="schedule_assignment_one_target",
            )
        ]

    def clean(self):
        super().clean()
        validate_date_range(self.effective_from, self.effective_to)
        if self.work_schedule_id:
            validate_same_school(self, self.work_schedule)
        if self.department_id:
            validate_same_school(self, self.department)
        if self.staff_profile_id:
            validate_same_school(self, self.staff_profile)
        if self.assigned_by_id and self.assigned_by.school_id != self.school_id:
            raise ValidationError({"assigned_by": "The assigner must belong to this school."})
        if bool(self.department_id) == bool(self.staff_profile_id):
            raise ValidationError(
                "Exactly one of department or staff_profile must be set."
            )
        target_field = "department" if self.department_id else "staff_profile"
        target_id = self.department_id or self.staff_profile_id
        if target_id and self.effective_from:
            overlap = type(self).objects.filter(
                **{
                    f"{target_field}_id": target_id,
                    "effective_from__lte": self.effective_to or date.max,
                }
            ).filter(
                models.Q(effective_to__isnull=True)
                | models.Q(effective_to__gte=self.effective_from)
            )
            if self.pk:
                overlap = overlap.exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError(
                    {"effective_from": "Assignments for this target cannot overlap."}
                )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.work_schedule_id:
                WorkSchedule.objects.select_for_update().get(pk=self.work_schedule_id)
            if self.department_id:
                type(self.department).objects.select_for_update().get(
                    pk=self.department_id
                )
            elif self.staff_profile_id:
                type(self.staff_profile).objects.select_for_update().get(
                    pk=self.staff_profile_id
                )
            return super().save(*args, **kwargs)


class ScheduleException(SchoolOwnedModel):
    staff_profile = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="schedule_exceptions"
    )
    exception_date = models.DateField()
    is_working_day = models.BooleanField(default=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    late_after = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_schedule_exceptions",
    )

    class Meta:
        ordering = ["exception_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff_profile", "exception_date"],
                name="staff_schedule_exception_date_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_time__isnull=True)
                    | models.Q(end_time__isnull=True)
                    | models.Q(end_time__gt=models.F("start_time"))
                ),
                name="schedule_exception_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        if self.staff_profile_id:
            validate_same_school(self, self.staff_profile)
        if self.created_by_id and self.created_by.school_id != self.school_id:
            raise ValidationError({"created_by": "The creator must belong to this school."})
