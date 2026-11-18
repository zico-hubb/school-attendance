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
from schools.models import Department
from schools.serializers import DepartmentSerializer, DepartmentWriteSerializer


def json_safe_data(data):
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def save_department(serializer, request, action, before_data=None):
    try:
        with transaction.atomic():
            department = serializer.save()
            after_data = json_safe_data(dict(DepartmentSerializer(department).data))
            AuditLog.objects.create(
                school=request.user.school,
                actor_user=request.user,
                action=action,
                entity_type="Department",
                entity_id=department.pk,
                before_data=(
                    json_safe_data(before_data) if before_data is not None else None
                ),
                after_data=after_data,
            )
        return department
    except DjangoValidationError as error:
        detail = error.message_dict if hasattr(error, "message_dict") else error.messages
        raise serializers.ValidationError(detail) from error
    except IntegrityError as error:
        raise serializers.ValidationError(
            {"name": "A department with this name already exists in this school."}
        ) from error


class DepartmentAPIView(APIView):
    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            permission_classes = [IsAuthenticated, IsSchoolAdminOrAttendanceManager]
        else:
            permission_classes = [IsAuthenticated, IsSchoolAdmin]
        return [permission() for permission in permission_classes]


class DepartmentListCreateView(DepartmentAPIView):
    def get(self, request, version):
        departments = Department.objects.filter(school=request.user.school)
        return Response(DepartmentSerializer(departments, many=True).data)

    def post(self, request, version):
        serializer = DepartmentWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        department = save_department(
            serializer, request, "DEPARTMENT_CREATED"
        )
        return Response(
            DepartmentSerializer(department).data,
            status=status.HTTP_201_CREATED,
        )


class DepartmentDetailView(DepartmentAPIView):
    def get_queryset(self, request):
        return Department.objects.filter(school=request.user.school)

    def get(self, request, version, department_id):
        department = get_object_or_404(
            self.get_queryset(request), pk=department_id
        )
        return Response(DepartmentSerializer(department).data)

    def patch(self, request, version, department_id):
        department = get_object_or_404(
            self.get_queryset(request), pk=department_id
        )
        before_data = dict(DepartmentSerializer(department).data)
        serializer = DepartmentWriteSerializer(
            department,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data.get(
            "is_active", department.is_active
        )
        if requested_status != department.is_active:
            action = (
                "DEPARTMENT_ACTIVATED"
                if requested_status
                else "DEPARTMENT_DEACTIVATED"
            )
        else:
            action = "DEPARTMENT_UPDATED"
        department = save_department(
            serializer, request, action, before_data
        )
        return Response(DepartmentSerializer(department).data)
