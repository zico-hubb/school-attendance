from django.core.exceptions import ValidationError
from django.db import models

from common.models import TimestampedModel


class School(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        INACTIVE = "INACTIVE", "Inactive"

    school_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ["name", "school_code"]

    def save(self, *args, **kwargs):
        if self.pk:
            previous_code = (
                type(self).objects.filter(pk=self.pk)
                .values_list("school_code", flat=True)
                .first()
            )
            if previous_code is not None and previous_code != self.school_code:
                raise ValidationError({"school_code": "School codes are immutable."})
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.school_code})"


class Department(TimestampedModel):
    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="departments"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="school_department_name_uniq"
            )
        ]

    def clean(self):
        super().clean()
        if self.school_id and self.pk:
            previous_school = (
                type(self).objects.filter(pk=self.pk)
                .values_list("school_id", flat=True)
                .first()
            )
            if previous_school is not None and previous_school != self.school_id:
                raise ValidationError({"school": "A department cannot change schools."})

    def __str__(self):
        return self.name
