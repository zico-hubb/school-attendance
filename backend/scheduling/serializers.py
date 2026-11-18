from rest_framework import serializers

from staff.models import StaffProfile

from .models import (
    ScheduleAssignment,
    ScheduleDay,
    ScheduleException,
    ScheduleVersion,
    WorkSchedule,
)


class StrictSerializerMixin:
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class ScheduleDayInputSerializer(StrictSerializerMixin, serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    is_working_day = serializers.BooleanField()
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    late_after = serializers.TimeField(required=False, allow_null=True)
    absence_finalization_time = serializers.TimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["is_working_day"]:
            if attrs.get("start_time") is None or attrs.get("end_time") is None:
                raise serializers.ValidationError(
                    "Working days require start_time and end_time."
                )
            if (
                attrs.get("late_after") is None
                or attrs.get("absence_finalization_time") is None
            ):
                raise serializers.ValidationError(
                    "Working days require late_after and absence_finalization_time."
                )
            if attrs["end_time"] <= attrs["start_time"]:
                raise serializers.ValidationError(
                    {"end_time": "End time must be after start time."}
                )
        elif any(
            attrs.get(field) is not None
            for field in (
                "start_time",
                "end_time",
                "late_after",
                "absence_finalization_time",
            )
        ):
            raise serializers.ValidationError(
                "Non-working days cannot define attendance times."
            )
        return attrs


class ScheduleDaysInputSerializer(StrictSerializerMixin, serializers.Serializer):
    days = ScheduleDayInputSerializer(many=True)

    def validate_days(self, days):
        weekdays = [item["weekday"] for item in days]
        if len(weekdays) != 7 or set(weekdays) != set(range(7)):
            raise serializers.ValidationError(
                "Provide exactly one entry for each weekday (0 through 6)."
            )
        return days


class ScheduleCreateSerializer(ScheduleDaysInputSerializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True)
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)


class ScheduleVersionCreateSerializer(ScheduleDaysInputSerializer):
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)


class ScheduleDayReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleDay
        fields = [
            "weekday",
            "is_working_day",
            "start_time",
            "end_time",
            "late_after",
            "absence_finalization_time",
        ]


class ScheduleVersionReadSerializer(serializers.ModelSerializer):
    days = ScheduleDayReadSerializer(many=True, read_only=True)

    class Meta:
        model = ScheduleVersion
        fields = [
            "id",
            "version_number",
            "effective_from",
            "effective_to",
            "is_active",
            "days",
            "created_at",
        ]


class WorkScheduleReadSerializer(serializers.ModelSerializer):
    versions = ScheduleVersionReadSerializer(many=True, read_only=True)

    class Meta:
        model = WorkSchedule
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "versions",
            "created_at",
            "updated_at",
        ]


class WorkScheduleUpdateSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = WorkSchedule
        fields = ["name", "description", "is_active"]


class ScheduleAssignmentReadSerializer(serializers.ModelSerializer):
    work_schedule_name = serializers.CharField(source="work_schedule.name", read_only=True)
    department_name = serializers.CharField(
        source="department.name", read_only=True, allow_null=True
    )
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleAssignment
        fields = [
            "id",
            "work_schedule",
            "work_schedule_name",
            "department",
            "department_name",
            "staff_profile",
            "staff_name",
            "is_school_default",
            "effective_from",
            "effective_to",
        ]

    def get_staff_name(self, obj):
        if obj.staff_profile_id is None:
            return None
        return obj.staff_profile.user.get_full_name() or obj.staff_profile.employee_number


class ScheduleAssignmentWriteSerializer(
    StrictSerializerMixin, serializers.ModelSerializer
):
    work_schedule = serializers.PrimaryKeyRelatedField(queryset=WorkSchedule.objects.none())
    department = serializers.PrimaryKeyRelatedField(
        queryset=ScheduleAssignment._meta.get_field("department").remote_field.model.objects.none(),
        required=False,
        allow_null=True,
    )
    staff_profile = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.none(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ScheduleAssignment
        fields = [
            "work_schedule",
            "department",
            "staff_profile",
            "is_school_default",
            "effective_from",
            "effective_to",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context["request"]
        school = request.user.school
        self.fields["work_schedule"].queryset = WorkSchedule.objects.filter(
            school=school, is_active=True
        )
        self.fields["department"].queryset = self.fields["department"].queryset.filter(
            school=school, is_active=True
        )
        self.fields["staff_profile"].queryset = self.fields[
            "staff_profile"
        ].queryset.filter(
            school=school,
            employment_status=StaffProfile.EmploymentStatus.ACTIVE,
        )

    def create(self, validated_data):
        request = self.context["request"]
        return ScheduleAssignment.objects.create(
            school=request.user.school,
            assigned_by=request.user,
            **validated_data,
        )


class ScheduleAssignmentEndSerializer(StrictSerializerMixin, serializers.Serializer):
    effective_to = serializers.DateField(allow_null=True)


class ScheduleExceptionReadSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleException
        fields = [
            "id",
            "staff_profile",
            "staff_name",
            "exception_date",
            "is_working_day",
            "start_time",
            "end_time",
            "late_after",
            "absence_finalization_time",
            "reason",
        ]

    def get_staff_name(self, obj):
        return obj.staff_profile.user.get_full_name() or obj.staff_profile.employee_number


class ScheduleExceptionWriteSerializer(
    StrictSerializerMixin, serializers.ModelSerializer
):
    staff_profile = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.none()
    )

    class Meta:
        model = ScheduleException
        fields = [
            "staff_profile",
            "exception_date",
            "is_working_day",
            "start_time",
            "end_time",
            "late_after",
            "absence_finalization_time",
            "reason",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff_profile"].queryset = self.fields[
            "staff_profile"
        ].queryset.filter(
            school=self.context["request"].user.school,
            employment_status=StaffProfile.EmploymentStatus.ACTIVE,
        )

    def validate(self, attrs):
        values = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in (
                "start_time",
                "end_time",
                "late_after",
                "absence_finalization_time",
            )
        }
        working = attrs.get(
            "is_working_day",
            getattr(self.instance, "is_working_day", True),
        )
        if (
            values["start_time"] is not None
            and values["end_time"] is not None
        ):
            if values["end_time"] <= values["start_time"]:
                raise serializers.ValidationError(
                    {"end_time": "End time must be after start time."}
                )
        elif values["start_time"] is not None or values["end_time"] is not None:
            raise serializers.ValidationError(
                "Provide both start_time and end_time, or neither."
            )
        if not working and (
            any(value is not None for value in values.values())
        ):
            raise serializers.ValidationError(
                "A non-working exception cannot define attendance times."
            )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return ScheduleException.objects.create(
            school=request.user.school,
            created_by=request.user,
            **validated_data,
        )
