from django.core.exceptions import ValidationError
from django.db import models

from common.models import SchoolOwnedModel, validate_same_school


class StaffProfile(SchoolOwnedModel):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ON_LEAVE = "ON_LEAVE", "On leave"
        TERMINATED = "TERMINATED", "Terminated"

    user = models.OneToOneField(
        "accounts.User", on_delete=models.PROTECT, related_name="staff_profile"
    )
    employee_number = models.CharField(max_length=64)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    department = models.ForeignKey(
        "schools.Department",
        on_delete=models.PROTECT,
        related_name="staff_profiles",
        null=True,
        blank=True,
    )
    job_title = models.CharField(max_length=120, blank=True)
    employment_status = models.CharField(
        max_length=16,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    date_joined = models.DateField()
    date_left = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["employee_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "employee_number"],
                name="staff_school_employee_number_uniq",
            )
        ]

    def clean(self):
        super().clean()
        if self.user_id:
            validate_same_school(self, self.user)
        if self.department_id:
            validate_same_school(self, self.department)
        if self.date_left and self.date_left < self.date_joined:
            raise ValidationError({"date_left": "Date left cannot precede date joined."})

    def __str__(self):
        return f"{self.employee_number}: {self.first_name} {self.last_name}"
