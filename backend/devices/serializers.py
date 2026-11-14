from rest_framework import serializers


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {"detail": "The request contains unsupported fields."}
                )
        return super().to_internal_value(data)


class EnrollmentSerializer(StrictInputSerializer):
    platform = serializers.ChoiceField(choices=("ANDROID", "IOS"))
    device_name = serializers.CharField(max_length=120)
    public_key = serializers.CharField(max_length=2048, write_only=True)
    challenge = serializers.CharField(max_length=128, write_only=True)
    signature = serializers.CharField(max_length=256, write_only=True)


class DeviceAuthenticationSerializer(StrictInputSerializer):
    challenge = serializers.CharField(max_length=128, write_only=True)
    signature = serializers.CharField(max_length=256, write_only=True)


class DeviceReasonSerializer(StrictInputSerializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
