from rest_framework import serializers

from .models import Department


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DepartmentWriteSerializer(StrictModelSerializer):
    class Meta:
        model = Department
        fields = ["name", "description", "is_active"]

    def validate_name(self, value):
        school = self.context["request"].user.school
        queryset = Department.objects.filter(school=school, name=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A department with this name already exists in this school."
            )
        return value

    def create(self, validated_data):
        return Department.objects.create(
            school=self.context["request"].user.school,
            **validated_data,
        )
