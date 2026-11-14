import uuid

from django.core.exceptions import ValidationError
from django.db import models

from common.models import (
    AppendOnlyModel,
    SchoolOwnedCreatedModel,
    SchoolOwnedModel,
    validate_same_school,
)


class RegisteredDevice(SchoolOwnedModel):
    class Platform(models.TextChoices):
        ANDROID = "ANDROID", "Android"
        IOS = "IOS", "iOS"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        REVOKED = "REVOKED", "Revoked"
        REJECTED = "REJECTED", "Rejected"

    staff_profile = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="devices"
    )
    platform = models.CharField(max_length=8, choices=Platform.choices)
    device_name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING
    )
    enrolled_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff_profile"],
                condition=models.Q(status="ACTIVE"),
                name="one_active_device_per_staff",
            )
        ]

    def clean(self):
        super().clean()
        if self.staff_profile_id:
            validate_same_school(self, self.staff_profile)
        if self.status == self.Status.REVOKED and not self.revoked_at:
            raise ValidationError({"revoked_at": "Revoked devices require a revocation time."})


class DeviceKey(SchoolOwnedCreatedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RETIRED = "RETIRED", "Retired"
        REVOKED = "REVOKED", "Revoked"

    device = models.ForeignKey(
        RegisteredDevice, on_delete=models.PROTECT, related_name="keys"
    )
    public_key = models.TextField()
    algorithm = models.CharField(max_length=32)
    fingerprint = models.CharField(max_length=128, unique=True)
    key_version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.ACTIVE
    )
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["device_id", "-key_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["device"],
                condition=models.Q(status="ACTIVE"),
                name="one_active_key_per_device",
            ),
            models.UniqueConstraint(
                fields=["device", "key_version"], name="device_key_version_uniq"
            ),
        ]

    def clean(self):
        super().clean()
        if self.device_id:
            validate_same_school(self, self.device)
        if self.status in {self.Status.RETIRED, self.Status.REVOKED} and not self.retired_at:
            raise ValidationError({"retired_at": "Inactive keys require a retirement time."})


class DeviceEvent(AppendOnlyModel):
    class EventType(models.TextChoices):
        ENROLLMENT = "ENROLLMENT", "Enrollment"
        APPROVAL = "APPROVAL", "Approval"
        REVOCATION = "REVOCATION", "Revocation"
        REPLACEMENT = "REPLACEMENT", "Replacement"
        KEY_ROTATION = "KEY_ROTATION", "Key rotation"
        REJECTION = "REJECTION", "Rejection"

    device = models.ForeignKey(
        RegisteredDevice, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        super().clean()
        if self.device_id:
            validate_same_school(self, self.device)


class UserSession(SchoolOwnedModel):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="sessions"
    )
    device = models.ForeignKey(
        RegisteredDevice,
        on_delete=models.PROTECT,
        related_name="sessions",
        null=True,
        blank=True,
    )
    refresh_token_hash = models.CharField(max_length=128)
    token_family_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["refresh_token_hash"], name="session_refresh_hash_uniq"
            )
        ]

    def clean(self):
        super().clean()
        related = [self.user]
        if self.device_id:
            related.append(self.device)
            if self.device.staff_profile.user_id != self.user_id:
                raise ValidationError(
                    {"device": "The device must belong to the session user."}
                )
        validate_same_school(self, *related)


class SessionRefreshToken(SchoolOwnedCreatedModel):
    session = models.ForeignKey(
        UserSession, on_delete=models.PROTECT, related_name="refresh_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        super().clean()
        if self.session_id:
            validate_same_school(self, self.session)


class AuthenticationChallenge(SchoolOwnedModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="authentication_challenges",
        null=True,
        blank=True,
    )
    device = models.ForeignKey(
        RegisteredDevice,
        on_delete=models.PROTECT,
        related_name="authentication_challenges",
        null=True,
        blank=True,
    )
    purpose = models.CharField(max_length=64)
    challenge_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | models.Q(device__isnull=False),
                name="challenge_has_user_or_device",
            ),
            models.UniqueConstraint(
                fields=["challenge_hash"], name="auth_challenge_hash_uniq"
            ),
        ]

    def clean(self):
        super().clean()
        related = []
        if self.user_id:
            related.append(self.user)
        if self.device_id:
            related.append(self.device)
        validate_same_school(self, *related)
