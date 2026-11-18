from rest_framework import serializers

from schools.models import Department

from .models import LeaveRecord, LeaveType, SchoolCalendarEvent


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class LeaveTypeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class LeaveTypeWriteSerializer(StrictModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["name", "description", "is_active"]

    def validate_name(self, value):
        queryset = LeaveType.objects.filter(
            school=self.context["request"].user.school,
            name=value,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A leave type with this name already exists in this school."
            )
        return value

    def create(self, validated_data):
        return LeaveType.objects.create(
            school=self.context["request"].user.school,
            **validated_data,
        )


class LeaveRecordReadSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )
    cancelled_by_name = serializers.CharField(
        source="cancelled_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = LeaveRecord
        fields = [
            "id",
            "staff_profile",
            "staff_name",
            "leave_type",
            "leave_type_name",
            "start_date",
            "end_date",
            "reason",
            "status",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "review_comment",
            "cancelled_by",
            "cancelled_by_name",
            "cancelled_at",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]

    def get_staff_name(self, obj):
        return obj.staff_profile.user.get_full_name() or obj.staff_profile.employee_number


class LeaveApplicationWriteSerializer(StrictModelSerializer):
    leave_type = serializers.PrimaryKeyRelatedField(
        queryset=LeaveType.objects.none()
    )

    class Meta:
        model = LeaveRecord
        fields = ["leave_type", "start_date", "end_date", "reason"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["leave_type"].queryset = LeaveType.objects.filter(
            school=self.context["request"].user.school,
            is_active=True,
        )

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError(
                {"end_date": "End date must be on or after start date."}
            )
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        return LeaveRecord.objects.create(
            school=user.school,
            staff_profile=user.staff_profile,
            **validated_data,
        )


class LeaveReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[LeaveRecord.Status.APPROVED, LeaveRecord.Status.REJECTED]
    )
    review_comment = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class LeaveCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField()

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class SchoolCalendarEventReadSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(
        source="department.name", read_only=True, allow_null=True
    )

    class Meta:
        model = SchoolCalendarEvent
        fields = [
            "id",
            "name",
            "event_type",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "late_after",
            "absence_finalization_time",
            "department",
            "department_name",
            "description",
            "created_at",
            "updated_at",
        ]


class SchoolCalendarEventWriteSerializer(StrictModelSerializer):
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.none(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = SchoolCalendarEvent
        fields = [
            "name",
            "event_type",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "late_after",
            "absence_finalization_time",
            "department",
            "description",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(
            school=self.context["request"].user.school,
            is_active=True,
        )

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start is not None and end is not None and end < start:
            raise serializers.ValidationError(
                {"end_date": "End date must be on or after start date."}
            )
        event_type = attrs.get(
            "event_type",
            getattr(self.instance, "event_type", None),
        )
        time_fields = (
            "start_time",
            "end_time",
            "late_after",
            "absence_finalization_time",
        )
        times = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in time_fields
        }
        if event_type == SchoolCalendarEvent.EventType.EXCEPTIONAL_WORKING_DAY:
            if any(value is None for value in times.values()):
                raise serializers.ValidationError(
                    "Exceptional working days require start, end, late, and absence times."
                )
            if times["end_time"] <= times["start_time"]:
                raise serializers.ValidationError(
                    {"end_time": "End time must be after start time."}
                )
        elif any(value is not None for value in times.values()):
            raise serializers.ValidationError(
                "Only exceptional working days can define attendance times."
            )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return SchoolCalendarEvent.objects.create(
            school=request.user.school,
            created_by=request.user,
            **validated_data,
        )
