from datetime import date

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSchoolAdmin, IsSchoolAdminOrAttendanceManager
from attendance.models import AttendanceRecord
from audit.models import AuditLog
from devices.models import RegisteredDevice
from leave_management.models import LeaveRecord
from schools.models import School
from staff.models import StaffProfile


class SchoolOverviewView(APIView):
    permission_classes = [IsSchoolAdminOrAttendanceManager]

    def get(self, request, version):
        school = request.user.school
        today = timezone.localdate()
        active_staff = StaffProfile.objects.filter(
            school=school,
            employment_status=StaffProfile.EmploymentStatus.ACTIVE,
        )
        records = AttendanceRecord.objects.filter(
            school=school, attendance_date=today
        )
        return Response({
            "date": str(today),
            "school": {
                "id": str(school.pk),
                "name": school.name,
                "school_code": school.school_code,
                "timezone": school.timezone,
                "status": school.status,
            },
            "staff": {
                "total": active_staff.count(),
                "by_department": list(
                    active_staff.exclude(department=None).values(
                        "department__name"
                    ).annotate(count=Count("pk")).order_by("department__name")
                ),
            },
            "attendance": {
                "present": records.filter(status__in=[
                    AttendanceRecord.Status.PRESENT,
                    AttendanceRecord.Status.LATE,
                ]).count(),
                "late": records.filter(status=AttendanceRecord.Status.LATE).count(),
                "absent": records.filter(status=AttendanceRecord.Status.ABSENT).count(),
                "on_leave": records.filter(status=AttendanceRecord.Status.ON_LEAVE).count(),
                "incomplete": records.filter(status=AttendanceRecord.Status.INCOMPLETE).count(),
                "not_yet_checked_in": records.filter(
                    status=AttendanceRecord.Status.NOT_YET_CHECKED_IN
                ).count(),
            },
            "devices": {
                "active": RegisteredDevice.objects.filter(
                    school=school, status=RegisteredDevice.Status.ACTIVE
                ).count(),
                "pending": RegisteredDevice.objects.filter(
                    school=school, status=RegisteredDevice.Status.PENDING
                ).count(),
                "revoked": RegisteredDevice.objects.filter(
                    school=school, status=RegisteredDevice.Status.REVOKED
                ).count(),
            },
            "leave": {
                "pending": LeaveRecord.objects.filter(
                    school=school, status=LeaveRecord.Status.PENDING
                ).count(),
            },
        })


class ReportsView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get(self, request, version):
        try:
            date_from = date.fromisoformat(
                request.query_params.get("date_from", str(timezone.localdate()))
            )
            date_to = date.fromisoformat(
                request.query_params.get("date_to", str(timezone.localdate()))
            )
        except ValueError:
            raise serializers.ValidationError(
                {"detail": "date_from and date_to must use YYYY-MM-DD format."}
            )
        if date_from > date_to:
            raise serializers.ValidationError(
                {"detail": "date_from cannot be after date_to."}
            )
        records = AttendanceRecord.objects.filter(
            school=request.user.school,
            attendance_date__gte=date_from,
            attendance_date__lte=date_to,
        )
        summary = records.values("status").annotate(count=Count("pk")).order_by("status")
        by_staff = (
            records.values(
                "staff_profile_id",
                "staff_profile__employee_number",
                "staff_profile__first_name",
                "staff_profile__last_name",
                "staff_profile__department__name",
            )
            .annotate(
                records=Count("pk"),
                present=Count("pk", filter=Q(status=AttendanceRecord.Status.PRESENT)),
                late=Count("pk", filter=Q(status=AttendanceRecord.Status.LATE)),
                absent=Count("pk", filter=Q(status=AttendanceRecord.Status.ABSENT)),
                on_leave=Count("pk", filter=Q(status=AttendanceRecord.Status.ON_LEAVE)),
                incomplete=Count("pk", filter=Q(status=AttendanceRecord.Status.INCOMPLETE)),
            )
            .order_by("staff_profile__employee_number")
        )
        return Response({
            "date_from": str(date_from),
            "date_to": str(date_to),
            "summary": list(summary),
            "by_staff": list(by_staff),
        })


class AuditLogListView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get(self, request, version):
        logs = AuditLog.objects.filter(school=request.user.school)
        search = request.query_params.get("search", "").strip()
        action = request.query_params.get("action", "").strip()
        entity_type = request.query_params.get("entity_type", "").strip()
        if search:
            logs = logs.filter(
                Q(action__icontains=search)
                | Q(entity_type__icontains=search)
                | Q(reason__icontains=search)
            )
        if action:
            logs = logs.filter(action__iexact=action)
        if entity_type:
            logs = logs.filter(entity_type__iexact=entity_type)
        try:
            page_number = max(1, int(request.query_params.get("page", "1")))
            page_size = min(100, max(1, int(request.query_params.get("page_size", "25"))))
        except ValueError:
            raise serializers.ValidationError(
                {"detail": "page and page_size must be integers."}
            )
        page = Paginator(logs, page_size).get_page(page_number)
        return Response({
            "count": page.paginator.count,
            "page": page.number,
            "page_size": page_size,
            "total_pages": page.paginator.num_pages,
            "results": [
                {
                    "id": str(log.pk),
                    "action": log.action,
                    "entity_type": log.entity_type,
                    "entity_id": str(log.entity_id),
                    "actor_user_id": str(log.actor_user_id) if log.actor_user_id else None,
                    "before_data": log.before_data,
                    "after_data": log.after_data,
                    "reason": log.reason,
                    "created_at": log.created_at.isoformat(),
                }
                for log in page.object_list
            ],
        })


class SchoolSettingsSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64)

    def validate_timezone(self, value):
        try:
            __import__("zoneinfo").ZoneInfo(value)
        except Exception as error:
            raise serializers.ValidationError("Unknown IANA timezone.") from error
        return value


class SchoolSettingsView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get(self, request, version):
        school = request.user.school
        return Response({
            "id": str(school.pk),
            "school_code": school.school_code,
            "name": school.name,
            "email": school.email,
            "phone": school.phone,
            "address": school.address,
            "timezone": school.timezone,
            "status": school.status,
        })

    def patch(self, request, version):
        serializer = SchoolSettingsSerializer(
            data={
                "name": request.data.get("name", request.user.school.name),
                "email": request.data.get("email", request.user.school.email),
                "phone": request.data.get("phone", request.user.school.phone),
                "address": request.data.get("address", request.user.school.address),
                "timezone": request.data.get("timezone", request.user.school.timezone),
            }
        )
        serializer.is_valid(raise_exception=True)
        unknown = set(request.data) - {
            "name", "email", "phone", "address", "timezone"
        }
        if unknown:
            raise serializers.ValidationError(
                {"detail": "The request contains unsupported fields."}
            )
        school = School.objects.select_for_update().get(pk=request.user.school_id)
        for field, value in serializer.validated_data.items():
            setattr(school, field, value)
        school.save(update_fields=[
            "name", "email", "phone", "address", "timezone", "updated_at"
        ])
        from devices.services import record_audit
        record_audit(
            school=school,
            actor=request.user,
            action="SCHOOL_SETTINGS_UPDATED",
            entity_type="School",
            entity_id=school.pk,
            after_data=serializer.validated_data,
        )
        return Response({
            "id": str(school.pk),
            "school_code": school.school_code,
            "name": school.name,
            "email": school.email,
            "phone": school.phone,
            "address": school.address,
            "timezone": school.timezone,
            "status": school.status,
        })
