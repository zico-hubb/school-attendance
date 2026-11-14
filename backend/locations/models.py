import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import SchoolOwnedModel


_BSSID_PATTERNS = (
    r"[0-9A-F]{12}",
    r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}",
    r"(?:[0-9A-F]{2}-){5}[0-9A-F]{2}",
    r"(?:[0-9A-F]{4}\.){2}[0-9A-F]{4}",
)


def normalize_bssid(value):
    normalized = value.strip().upper()
    if not any(re.fullmatch(pattern, normalized) for pattern in _BSSID_PATTERNS):
        raise ValidationError({"normalized_bssid": "Enter a valid 6-byte BSSID."})
    compact = re.sub(r"[:-]|\.", "", normalized)
    if compact == "000000000000" or int(compact[:2], 16) & 1:
        raise ValidationError(
            {"normalized_bssid": "Enter a unicast BSSID address."}
        )
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


class AttendanceZone(SchoolOwnedModel):
    name = models.CharField(max_length=120)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    radius_meters = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90) & models.Q(latitude__lte=90),
                name="attendance_zone_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180)
                & models.Q(longitude__lte=180),
                name="attendance_zone_longitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(radius_meters__gt=0),
                name="attendance_zone_radius_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    radius_meters__lte=settings.ATTENDANCE_ZONE_RADIUS_DB_LIMIT_METERS
                ),
                name="attendance_zone_radius_maximum",
            ),
            models.UniqueConstraint(
                fields=["school", "name"], name="attendance_zone_name_uniq"
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.radius_meters is not None
            and self.radius_meters > settings.MAX_ATTENDANCE_ZONE_RADIUS_METERS
        ):
            raise ValidationError(
                {
                    "radius_meters": (
                        "Radius cannot exceed "
                        f"{settings.MAX_ATTENDANCE_ZONE_RADIUS_METERS} metres."
                    )
                }
            )


class ApprovedAccessPoint(SchoolOwnedModel):
    attendance_zone = models.ForeignKey(
        AttendanceZone, on_delete=models.PROTECT, related_name="access_points"
    )
    normalized_bssid = models.CharField(max_length=17)
    label = models.CharField(max_length=120, blank=True)
    location_notes = models.CharField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["normalized_bssid"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "normalized_bssid"],
                name="school_normalized_bssid_uniq",
            )
        ]

    def clean(self):
        super().clean()
        if self.attendance_zone_id and self.attendance_zone.school_id != self.school_id:
            raise ValidationError(
                {"attendance_zone": "The zone must belong to the same school."}
            )
        if self.normalized_bssid:
            self.normalized_bssid = normalize_bssid(self.normalized_bssid)

    def save(self, *args, **kwargs):
        if self.normalized_bssid:
            self.normalized_bssid = normalize_bssid(self.normalized_bssid)
        return super().save(*args, **kwargs)
