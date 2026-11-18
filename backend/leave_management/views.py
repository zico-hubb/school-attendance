import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    IsAuthenticated,
    IsSchoolAdmin,
    IsSchoolAdminOrAttendanceManager,
)
from audit.models import AuditLog

from .models import LeaveRecord, LeaveType, SchoolCalendarEvent
from .serializers import (
    LeaveApplicationWriteSerializer,
    LeaveCancelSerializer,
    LeaveRecordReadSerializer,
    LeaveReviewSerializer,
    LeaveTypeReadSerializer,
    LeaveTypeWriteSerializer,
    SchoolCalendarEventReadSerializer,
    SchoolCalendarEventWriteSerializer,
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


class LeaveTypeAPIView(APIView):
    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            classes = [IsAuthenticated]
        else:
            classes = [IsAuthenticated, IsSchoolAdmin]
        return [permission() for permission in classes]


class LeaveTypeListCreateView(LeaveTypeAPIView):
    def get(self, request, version):
        types = LeaveType.objects.filter(school=request.user.school)
        if request.user.role == request.user.Role.STAFF:
            types = types.filter(is_active=True)
        elif request.user.role not in {
            request.user.Role.SCHOOL_ADMIN,
            request.user.Role.ATTENDANCE_MANAGER,
        }:
            raise PermissionDenied("Leave type access is not available for this role.")
        types = types.order_by("name")
        return Response(LeaveTypeReadSerializer(types, many=True).data)

    def post(self, request, version):
        serializer = LeaveTypeWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                leave_type = serializer.save()
                _audit(
                    request,
                    "LEAVE_TYPE_CREATED",
                    leave_type,
                    after=LeaveTypeReadSerializer(leave_type).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"name": "A leave type with this name already exists."}
            ) from error
        return Response(
            LeaveTypeReadSerializer(leave_type).data,
            status=status.HTTP_201_CREATED,
        )


class LeaveTypeDetailView(LeaveTypeAPIView):
    def patch(self, request, version, leave_type_id):
        leave_type = get_object_or_404(
            LeaveType.objects.filter(school=request.user.school),
            pk=leave_type_id,
        )
        before = LeaveTypeReadSerializer(leave_type).data
        serializer = LeaveTypeWriteSerializer(
            leave_type,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                leave_type = serializer.save()
                _audit(
                    request,
                    "LEAVE_TYPE_UPDATED",
                    leave_type,
                    before=before,
                    after=LeaveTypeReadSerializer(leave_type).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"name": "A leave type with this name already exists."}
            ) from error
        return Response(LeaveTypeReadSerializer(leave_type).data)


class LeaveRecordListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self, request):
        records = LeaveRecord.objects.filter(school=request.user.school).select_related(
            "staff_profile__user",
            "leave_type",
            "reviewed_by",
            "cancelled_by",
        )
        if request.user.role == request.user.Role.STAFF:
            return records.filter(staff_profile__user=request.user)
        return records

    def get(self, request, version):
        return Response(
            LeaveRecordReadSerializer(self.get_queryset(request), many=True).data
        )

    def post(self, request, version):
        if request.user.role != request.user.Role.STAFF:
            raise PermissionDenied(
                "Only staff members may submit a leave request."
            )
        if not hasattr(request.user, "staff_profile"):
            raise serializers.ValidationError(
                {"detail": "The user does not have a staff profile."}
            )
        serializer = LeaveApplicationWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                record = serializer.save()
                record = self.get_queryset(request).get(pk=record.pk)
                _audit(
                    request,
                    "LEAVE_REQUEST_SUBMITTED",
                    record,
                    after=LeaveRecordReadSerializer(record).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"detail": "The leave request conflicts with an existing record."}
            ) from error
        return Response(
            LeaveRecordReadSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class LeaveRecordReviewView(APIView):
    permission_classes = [IsAuthenticated, IsSchoolAdmin]

    def post(self, request, version, leave_id):
        try:
            with transaction.atomic():
                record = get_object_or_404(
                    LeaveRecord.objects.filter(school=request.user.school)
                    .select_related("staff_profile__user", "leave_type")
                    .select_for_update(),
                    pk=leave_id,
                )
                if record.status != LeaveRecord.Status.PENDING:
                    raise serializers.ValidationError(
                        {"status": "Only pending leave requests can be reviewed."}
                    )
                serializer = LeaveReviewSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                before = LeaveRecordReadSerializer(record).data
                record.status = serializer.validated_data["status"]
                record.review_comment = serializer.validated_data.get(
                    "review_comment", ""
                )
                record.reviewed_by = request.user
                record.reviewed_at = timezone.now()
                record.save()
                record = LeaveRecord.objects.select_related(
                    "staff_profile__user", "leave_type", "reviewed_by", "cancelled_by"
                ).get(pk=record.pk)
                _audit(
                    request,
                    "LEAVE_REQUEST_REVIEWED",
                    record,
                    before=before,
                    after=LeaveRecordReadSerializer(record).data,
                    reason=record.review_comment,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"start_date": "Approved leave overlaps another approved request."}
            ) from error
        return Response(LeaveRecordReadSerializer(record).data)


class LeaveRecordCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version, leave_id):
        serializer = LeaveCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                record = get_object_or_404(
                    LeaveRecord.objects.filter(school=request.user.school)
                    .select_related("staff_profile__user", "leave_type")
                    .select_for_update(),
                    pk=leave_id,
                )
                is_owner = record.staff_profile.user_id == request.user.pk
                is_admin = request.user.role == request.user.Role.SCHOOL_ADMIN
                if not is_owner and not is_admin:
                    raise PermissionDenied(
                        "Only the requester or a school administrator may cancel this leave."
                    )
                if is_owner and record.status != LeaveRecord.Status.PENDING:
                    raise serializers.ValidationError(
                        {"status": "Staff may cancel only pending leave requests."}
                    )
                if record.status not in {
                    LeaveRecord.Status.PENDING,
                    LeaveRecord.Status.APPROVED,
                }:
                    raise serializers.ValidationError(
                        {"status": "This leave request can no longer be cancelled."}
                    )
                before = LeaveRecordReadSerializer(record).data
                reason = serializer.validated_data["cancellation_reason"]
                record.status = LeaveRecord.Status.CANCELLED
                record.cancelled_by = request.user
                record.cancelled_at = timezone.now()
                record.cancellation_reason = reason
                record.save()
                record = LeaveRecord.objects.select_related(
                    "staff_profile__user", "leave_type", "reviewed_by", "cancelled_by"
                ).get(pk=record.pk)
                _audit(
                    request,
                    "LEAVE_REQUEST_CANCELLED",
                    record,
                    before=before,
                    after=LeaveRecordReadSerializer(record).data,
                    reason=reason,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        return Response(LeaveRecordReadSerializer(record).data)


class SchoolCalendarEventAPIView(APIView):
    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            classes = [IsAuthenticated, IsSchoolAdminOrAttendanceManager]
        else:
            classes = [IsAuthenticated, IsSchoolAdmin]
        return [permission() for permission in classes]


class SchoolCalendarEventListCreateView(SchoolCalendarEventAPIView):
    def get(self, request, version):
        events = SchoolCalendarEvent.objects.filter(
            school=request.user.school
        ).select_related("department")
        return Response(
            SchoolCalendarEventReadSerializer(events, many=True).data
        )

    def post(self, request, version):
        serializer = SchoolCalendarEventWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                event = serializer.save()
                _audit(
                    request,
                    "SCHOOL_CALENDAR_EVENT_CREATED",
                    event,
                    after=SchoolCalendarEventReadSerializer(event).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        return Response(
            SchoolCalendarEventReadSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )


class SchoolCalendarEventDetailView(SchoolCalendarEventAPIView):
    def patch(self, request, version, event_id):
        event = get_object_or_404(
            SchoolCalendarEvent.objects.filter(
                school=request.user.school
            ).select_related("department"),
            pk=event_id,
        )
        before = SchoolCalendarEventReadSerializer(event).data
        serializer = SchoolCalendarEventWriteSerializer(
            event,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                event = serializer.save()
                _audit(
                    request,
                    "SCHOOL_CALENDAR_EVENT_UPDATED",
                    event,
                    before=before,
                    after=SchoolCalendarEventReadSerializer(event).data,
                )
        except DjangoValidationError as error:
            _validation_error(error)
        return Response(SchoolCalendarEventReadSerializer(event).data)
