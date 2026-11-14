from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    ApprovedAccessPoint,
    AttendanceZone,
    normalize_bssid,
)


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class AttendanceZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceZone
        fields = [
            "id",
            "name",
            "latitude",
            "longitude",
            "radius_meters",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AttendanceZoneWriteSerializer(StrictModelSerializer):
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180
    )
    radius_meters = serializers.IntegerField(min_value=1)

    class Meta:
        model = AttendanceZone
        fields = [
            "name",
            "latitude",
            "longitude",
            "radius_meters",
            "is_active",
        ]
        validators = []

    def validate_name(self, value):
        school = self.context["request"].user.school
        queryset = AttendanceZone.objects.filter(school=school, name=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A zone with this name already exists in this school."
            )
        return value

    def validate_radius_meters(self, value):
        if value > settings.MAX_ATTENDANCE_ZONE_RADIUS_METERS:
            raise serializers.ValidationError(
                "Radius exceeds the configured maximum of "
                f"{settings.MAX_ATTENDANCE_ZONE_RADIUS_METERS} metres."
            )
        return value

    def create(self, validated_data):
        return AttendanceZone.objects.create(
            school=self.context["request"].user.school,
            **validated_data,
        )


class ApprovedAccessPointSerializer(serializers.ModelSerializer):
    bssid = serializers.CharField(source="normalized_bssid", read_only=True)
    name = serializers.CharField(source="label", read_only=True)

    class Meta:
        model = ApprovedAccessPoint
        fields = [
            "id",
            "attendance_zone",
            "bssid",
            "name",
            "location_notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ApprovedAccessPointCreateSerializer(StrictModelSerializer):
    bssid = serializers.CharField(source="normalized_bssid", max_length=32)
    name = serializers.CharField(source="label", max_length=120)
    attendance_zone = serializers.PrimaryKeyRelatedField(
        queryset=AttendanceZone.objects.none()
    )
    location_notes = serializers.CharField(
        max_length=500, required=False, allow_blank=True
    )

    class Meta:
        model = ApprovedAccessPoint
        fields = ["attendance_zone", "bssid", "name", "location_notes"]
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attendance_zone"].queryset = AttendanceZone.objects.filter(
            school=self.context["request"].user.school
        )

    def validate_bssid(self, value):
        try:
            normalized = normalize_bssid(value)
        except DjangoValidationError as error:
            message = (
                error.message_dict.get("normalized_bssid", error.messages)
                if hasattr(error, "message_dict")
                else error.messages
            )
            raise serializers.ValidationError(message) from error

        if ApprovedAccessPoint.objects.filter(
            school=self.context["request"].user.school,
            normalized_bssid=normalized,
        ).exists():
            raise serializers.ValidationError(
                "This BSSID is already registered in this school."
            )
        return normalized

    def create(self, validated_data):
        return ApprovedAccessPoint.objects.create(
            school=self.context["request"].user.school,
            **validated_data,
        )


class ApprovedAccessPointUpdateSerializer(StrictModelSerializer):
    name = serializers.CharField(source="label", max_length=120, required=False)
    location_notes = serializers.CharField(
        max_length=500, required=False, allow_blank=True
    )
    is_active = serializers.BooleanField(required=False)

    class Meta:
        model = ApprovedAccessPoint
        fields = ["name", "location_notes", "is_active"]
        validators = []
