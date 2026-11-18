import json
from datetime import timedelta

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

from .models import (
    ScheduleAssignment,
    ScheduleDay,
    ScheduleException,
    ScheduleVersion,
    WorkSchedule,
)
from .serializers import (
    ScheduleAssignmentEndSerializer,
    ScheduleAssignmentReadSerializer,
    ScheduleAssignmentWriteSerializer,
    ScheduleCreateSerializer,
    ScheduleExceptionReadSerializer,
    ScheduleExceptionWriteSerializer,
    ScheduleVersionCreateSerializer,
    WorkScheduleReadSerializer,
    WorkScheduleUpdateSerializer,
)


def _json_safe(data):
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def _audit(request, action, entity, before=None, after=None, reason=""):
    AuditLog.objects.create(
        school=request.user.school,
        actor_user=request.user,
        action=action,
        entity_type=type(entity).__name__,
        entity_id=entity.pk,
        before_data=_json_safe(before) if before is not None else None,
        after_data=_json_safe(after) if after is not None else None,
        reason=reason,
    )


def _validation_error(error):
    detail = error.message_dict if hasattr(error, "message_dict") else error.messages
    raise serializers.ValidationError(detail) from error


class ScheduleAPIView(APIView):
    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            classes = [IsAuthenticated, IsSchoolAdminOrAttendanceManager]
        else:
            classes = [IsAuthenticated, IsSchoolAdmin]
        return [permission() for permission in classes]


class WorkScheduleListCreateView(ScheduleAPIView):
    def get(self, request, version):
        schedules = (
            WorkSchedule.objects.filter(school=request.user.school)
            .prefetch_related("versions__days")
            .order_by("name")
        )
        return Response(WorkScheduleReadSerializer(schedules, many=True).data)

    def post(self, request, version):
        serializer = ScheduleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            with transaction.atomic():
                schedule = WorkSchedule.objects.create(
                    school=request.user.school,
                    name=values["name"],
                    description=values.get("description", ""),
                )
                schedule_version = ScheduleVersion.objects.create(
                    school=request.user.school,
                    work_schedule=schedule,
                    version_number=1,
                    effective_from=values["effective_from"],
                    effective_to=values.get("effective_to"),
                    created_by=request.user,
                )
                for day in values["days"]:
                    ScheduleDay.objects.create(
                        school=request.user.school,
                        schedule_version=schedule_version,
                        **day,
                    )
                schedule_version.activate()
                schedule = WorkSchedule.objects.prefetch_related(
                    "versions__days"
                ).get(pk=schedule.pk)
                _audit(
                    request,
                    "WORK_SCHEDULE_CREATED",
                    schedule,
                    after=WorkScheduleReadSerializer(schedule).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"name": "A work schedule with this name already exists."}
            ) from error
        return Response(
            WorkScheduleReadSerializer(schedule).data,
            status=status.HTTP_201_CREATED,
        )


class WorkScheduleDetailView(ScheduleAPIView):
    def get_schedule(self, request, schedule_id):
        return get_object_or_404(
            WorkSchedule.objects.filter(school=request.user.school).prefetch_related(
                "versions__days"
            ),
            pk=schedule_id,
        )

    def get(self, request, version, schedule_id):
        schedule = self.get_schedule(request, schedule_id)
        return Response(WorkScheduleReadSerializer(schedule).data)

    def patch(self, request, version, schedule_id):
        schedule = self.get_schedule(request, schedule_id)
        before = WorkScheduleReadSerializer(schedule).data
        serializer = WorkScheduleUpdateSerializer(
            schedule, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                schedule = serializer.save()
                _audit(
                    request,
                    "WORK_SCHEDULE_UPDATED",
                    schedule,
                    before=before,
                    after=WorkScheduleReadSerializer(schedule).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"name": "A work schedule with this name already exists."}
            ) from error
        return Response(WorkScheduleReadSerializer(schedule).data)


class ScheduleVersionListCreateView(ScheduleAPIView):
    def post(self, request, version, schedule_id):
        schedule = get_object_or_404(
            WorkSchedule.objects.filter(school=request.user.school),
            pk=schedule_id,
        )
        serializer = ScheduleVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            with transaction.atomic():
                schedule = WorkSchedule.objects.select_for_update().get(pk=schedule.pk)
                versions = list(
                    ScheduleVersion.objects.filter(work_schedule=schedule).order_by(
                        "-effective_from"
                    )
                )
                previous = versions[0] if versions else None
                before = (
                    {
                        "effective_from": previous.effective_from,
                        "effective_to": previous.effective_to,
                        "version_number": previous.version_number,
                    }
                    if previous is not None
                    else None
                )
                effective_from = values["effective_from"]
                if (
                    previous is not None
                    and previous.effective_to is None
                    and previous.effective_from < effective_from
                ):
                    previous.effective_to = effective_from - timedelta(days=1)
                    previous.save()
                schedule_version = ScheduleVersion.objects.create(
                    school=request.user.school,
                    work_schedule=schedule,
                    version_number=max(
                        (item.version_number for item in versions), default=0
                    )
                    + 1,
                    effective_from=effective_from,
                    effective_to=values.get("effective_to"),
                    created_by=request.user,
                )
                for day in values["days"]:
                    ScheduleDay.objects.create(
                        school=request.user.school,
                        schedule_version=schedule_version,
                        **day,
                    )
                schedule_version.activate()
                schedule = WorkSchedule.objects.prefetch_related(
                    "versions__days"
                ).get(pk=schedule.pk)
                _audit(
                    request,
                    "SCHEDULE_VERSION_CREATED",
                    schedule_version,
                    before=before,
                    after=WorkScheduleReadSerializer(schedule).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"effective_from": "The schedule version conflicts with an existing version."}
            ) from error
        return Response(
            WorkScheduleReadSerializer(schedule).data,
            status=status.HTTP_201_CREATED,
        )


class ScheduleAssignmentListCreateView(ScheduleAPIView):
    def get_queryset(self, request):
        return ScheduleAssignment.objects.filter(school=request.user.school).select_related(
            "work_schedule", "department", "staff_profile__user"
        )

    def get(self, request, version):
        return Response(
            ScheduleAssignmentReadSerializer(
                self.get_queryset(request), many=True
            ).data
        )

    def post(self, request, version):
        serializer = ScheduleAssignmentWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                assignment = serializer.save()
                _audit(
                    request,
                    "SCHEDULE_ASSIGNMENT_CREATED",
                    assignment,
                    after=ScheduleAssignmentReadSerializer(assignment).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"effective_from": "The schedule assignment conflicts with an existing assignment."}
            ) from error
        return Response(
            ScheduleAssignmentReadSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )


class ScheduleAssignmentDetailView(ScheduleAPIView):
    def patch(self, request, version, assignment_id):
        assignment = get_object_or_404(
            ScheduleAssignment.objects.filter(school=request.user.school).select_related(
                "work_schedule", "department", "staff_profile__user"
            ),
            pk=assignment_id,
        )
        before = ScheduleAssignmentReadSerializer(assignment).data
        serializer = ScheduleAssignmentEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment.effective_to = serializer.validated_data["effective_to"]
        try:
            with transaction.atomic():
                assignment.save()
                _audit(
                    request,
                    "SCHEDULE_ASSIGNMENT_UPDATED",
                    assignment,
                    before=before,
                    after=ScheduleAssignmentReadSerializer(assignment).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        return Response(ScheduleAssignmentReadSerializer(assignment).data)


class ScheduleExceptionListCreateView(ScheduleAPIView):
    def get_queryset(self, request):
        return ScheduleException.objects.filter(school=request.user.school).select_related(
            "staff_profile__user"
        )

    def get(self, request, version):
        return Response(
            ScheduleExceptionReadSerializer(self.get_queryset(request), many=True).data
        )

    def post(self, request, version):
        serializer = ScheduleExceptionWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                exception = serializer.save()
                _audit(
                    request,
                    "SCHEDULE_EXCEPTION_CREATED",
                    exception,
                    after=ScheduleExceptionReadSerializer(exception).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"exception_date": "An exception already exists for this staff member and date."}
            ) from error
        return Response(
            ScheduleExceptionReadSerializer(exception).data,
            status=status.HTTP_201_CREATED,
        )


class ScheduleExceptionDetailView(ScheduleAPIView):
    def patch(self, request, version, exception_id):
        exception = get_object_or_404(
            ScheduleException.objects.filter(
                school=request.user.school
            ).select_related("staff_profile__user"),
            pk=exception_id,
        )
        before = ScheduleExceptionReadSerializer(exception).data
        serializer = ScheduleExceptionWriteSerializer(
            exception,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                exception = serializer.save()
                _audit(
                    request,
                    "SCHEDULE_EXCEPTION_UPDATED",
                    exception,
                    before=before,
                    after=ScheduleExceptionReadSerializer(exception).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"exception_date": "An exception already exists for this staff member and date."}
            ) from error
        return Response(ScheduleExceptionReadSerializer(exception).data)
