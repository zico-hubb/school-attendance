from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from common.models import UUIDModel
from .managers import UserManager, normalize_username


class User(AbstractBaseUser, PermissionsMixin, UUIDModel):
    class Role(models.TextChoices):
        SCHOOL_ADMIN = "SCHOOL_ADMIN", "School admin"
        ATTENDANCE_MANAGER = "ATTENDANCE_MANAGER", "Attendance manager"
        STAFF = "STAFF", "Staff"

    school = models.ForeignKey(
        "schools.School", on_delete=models.PROTECT, related_name="users"
    )
    username = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.STAFF)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["school"]

    objects = UserManager()

    class Meta:
        ordering = ["school_id", "username"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "username"], name="user_school_username_uniq"
            )
        ]

    def clean(self):
        super().clean()
        if self.username:
            self.username = normalize_username(self.username)
        if self.school_id and self.pk:
            previous_school = (
                type(self).objects.filter(pk=self.pk)
                .values_list("school_id", flat=True)
                .first()
            )
            if previous_school is not None and previous_school != self.school_id:
                raise ValidationError({"school": "A user cannot change schools."})

    def save(self, *args, **kwargs):
        if self.username:
            self.username = normalize_username(self.username)
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_full_name(self):
        profile = getattr(self, "staff_profile", None)
        if profile:
            return f"{profile.first_name} {profile.last_name}".strip()
        return self.username

    def get_short_name(self):
        return self.username

    def __str__(self):
        return f"{self.school.school_code}:{self.username}"
