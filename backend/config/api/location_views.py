import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    IsAuthenticated,
    IsSchoolAdmin,
    IsSchoolAdminOrAttendanceManager,
)
from audit.models import AuditLog
from locations.models import ApprovedAccessPoint, AttendanceZone
from locations.serializers import (
    ApprovedAccessPointCreateSerializer,
    ApprovedAccessPointSerializer,
    ApprovedAccessPointUpdateSerializer,
    AttendanceZoneSerializer,
    AttendanceZoneWriteSerializer,
)


def translate_model_validation(error):
    detail = error.message_dict if hasattr(error, "message_dict") else error.messages
    raise serializers.ValidationError(detail) from error


def json_safe_data(data):
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def save_configuration(serializer, request, entity_type, action, before_data=None):
    try:
        with transaction.atomic():
            instance = serializer.save()
            response_serializer = (
                AttendanceZoneSerializer(instance)
                if entity_type == "AttendanceZone"
                else ApprovedAccessPointSerializer(instance)
            )
            after_data = json_safe_data(dict(response_serializer.data))
            AuditLog.objects.create(
                school=request.user.school,
                actor_user=request.user,
                action=action,
                entity_type=entity_type,
                entity_id=instance.pk,
                before_data=(
                    json_safe_data(before_data) if before_data is not None else None
                ),
                after_data=after_data,
            )
        return instance
    except DjangoValidationError as error:
        translate_model_validation(error)
    except IntegrityError as error:
        raise serializers.ValidationError(
            {"detail": "A configuration with this identity already exists in this school."}
        ) from error


class LocationConfigurationAPIView(APIView):
    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            permission_classes = [
                IsAuthenticated,
                IsSchoolAdminOrAttendanceManager,
            ]
        else:
            permission_classes = [IsAuthenticated, IsSchoolAdmin]
        return [permission() for permission in permission_classes]


class AttendanceZoneListCreateView(LocationConfigurationAPIView):
    def get(self, request, version):
        zones = AttendanceZone.objects.filter(school=request.user.school)
        return Response(AttendanceZoneSerializer(zones, many=True).data)

    def post(self, request, version):
        serializer = AttendanceZoneWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        zone = save_configuration(
            serializer,
            request,
            "AttendanceZone",
            "ATTENDANCE_ZONE_CREATED",
        )
        return Response(
            AttendanceZoneSerializer(zone).data,
            status=status.HTTP_201_CREATED,
        )


class AttendanceZoneDetailView(LocationConfigurationAPIView):
    def get_queryset(self, request):
        return AttendanceZone.objects.filter(school=request.user.school)

    def get(self, request, version, zone_id):
        zone = get_object_or_404(self.get_queryset(request), pk=zone_id)
        return Response(AttendanceZoneSerializer(zone).data)

    def patch(self, request, version, zone_id):
        zone = get_object_or_404(self.get_queryset(request), pk=zone_id)
        before_data = dict(AttendanceZoneSerializer(zone).data)
        serializer = AttendanceZoneWriteSerializer(
            zone,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data.get("is_active", zone.is_active)
        if requested_status != zone.is_active:
            action = (
                "ATTENDANCE_ZONE_ACTIVATED"
                if requested_status
                else "ATTENDANCE_ZONE_DEACTIVATED"
            )
        else:
            action = "ATTENDANCE_ZONE_UPDATED"
        zone = save_configuration(
            serializer,
            request,
            "AttendanceZone",
            action,
            before_data,
        )
        return Response(AttendanceZoneSerializer(zone).data)


class ApprovedAccessPointListCreateView(LocationConfigurationAPIView):
    def get(self, request, version):
        access_points = (
            ApprovedAccessPoint.objects.filter(school=request.user.school)
            .select_related("attendance_zone")
        )
        return Response(
            ApprovedAccessPointSerializer(access_points, many=True).data
        )

    def post(self, request, version):
        serializer = ApprovedAccessPointCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        access_point = save_configuration(
            serializer,
            request,
            "ApprovedAccessPoint",
            "ACCESS_POINT_REGISTERED",
        )
        return Response(
            ApprovedAccessPointSerializer(access_point).data,
            status=status.HTTP_201_CREATED,
        )


class ApprovedAccessPointDetailView(LocationConfigurationAPIView):
    def get_queryset(self, request):
        return ApprovedAccessPoint.objects.filter(school=request.user.school)

    def get(self, request, version, access_point_id):
        access_point = get_object_or_404(
            self.get_queryset(request), pk=access_point_id
        )
        return Response(ApprovedAccessPointSerializer(access_point).data)

    def patch(self, request, version, access_point_id):
        access_point = get_object_or_404(
            self.get_queryset(request), pk=access_point_id
        )
        before_data = dict(ApprovedAccessPointSerializer(access_point).data)
        serializer = ApprovedAccessPointUpdateSerializer(
            access_point,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data.get(
            "is_active", access_point.is_active
        )
        if requested_status != access_point.is_active:
            action = (
                "ACCESS_POINT_ACTIVATED"
                if requested_status
                else "ACCESS_POINT_DEACTIVATED"
            )
        else:
            action = "ACCESS_POINT_UPDATED"
        access_point = save_configuration(
            serializer,
            request,
            "ApprovedAccessPoint",
            action,
            before_data,
        )
        return Response(ApprovedAccessPointSerializer(access_point).data)
