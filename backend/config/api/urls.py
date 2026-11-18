from django.urls import path

from .auth_views import LoginView, LogoutView, PasswordChangeView, RefreshView
from .department_views import DepartmentDetailView, DepartmentListCreateView
from .device_views import (
    DeviceApproveView,
    DeviceAuthenticationChallengeView,
    DeviceDetailView,
    DeviceEnrollmentView,
    DeviceListView,
    DeviceRejectView,
    DeviceRevokeView,
    DeviceSessionView,
    EnrollmentChallengeView,
)
from .location_views import (
    ApprovedAccessPointDetailView,
    ApprovedAccessPointListCreateView,
    AttendanceZoneDetailView,
    AttendanceZoneListCreateView,
)
from leave_management.views import (
    LeaveRecordCancelView,
    LeaveRecordListCreateView,
    LeaveRecordReviewView,
    LeaveTypeDetailView,
    LeaveTypeListCreateView,
    SchoolCalendarEventDetailView,
    SchoolCalendarEventListCreateView,
)
from scheduling.views import (
    ScheduleAssignmentDetailView,
    ScheduleAssignmentListCreateView,
    ScheduleExceptionDetailView,
    ScheduleExceptionListCreateView,
    ScheduleVersionListCreateView,
    WorkScheduleDetailView,
    WorkScheduleListCreateView,
)
from .staff_views import StaffDetailView, StaffListCreateView
from .attendance_views import (
    AttendanceChallengeView,
    AttendanceCheckInView,
    AttendanceCheckOutView,
    AttendanceHistoryView,
    AttendanceRegisterView,
    AttendanceStatusView,
)
from .platform_views import (
    AuditLogListView,
    ReportsView,
    SchoolOverviewView,
    SchoolSettingsView,
)
from .views import health

app_name = "api"

urlpatterns = [
    path("health/", health, name="health"),
    path("overview/", SchoolOverviewView.as_view(), name="overview"),
    path("reports/attendance/", ReportsView.as_view(), name="attendance-report"),
    path("audit-logs/", AuditLogListView.as_view(), name="audit-log-list"),
    path("school-settings/", SchoolSettingsView.as_view(), name="school-settings"),
    path("attendance/challenge/", AttendanceChallengeView.as_view(), name="attendance-challenge"),
    path("attendance/check-in/", AttendanceCheckInView.as_view(), name="attendance-check-in"),
    path("attendance/check-out/", AttendanceCheckOutView.as_view(), name="attendance-check-out"),
    path("attendance/status/", AttendanceStatusView.as_view(), name="attendance-status"),
    path("attendance/history/", AttendanceHistoryView.as_view(), name="attendance-history"),
    path("attendance/register/", AttendanceRegisterView.as_view(), name="attendance-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path(
        "auth/password/change/",
        PasswordChangeView.as_view(),
        name="auth-password-change",
    ),
    path(
        "auth/device-challenge/",
        DeviceAuthenticationChallengeView.as_view(),
        name="auth-device-challenge",
    ),
    path(
        "auth/device-session/",
        DeviceSessionView.as_view(),
        name="auth-device-session",
    ),
    path(
        "devices/enrollment-challenge/",
        EnrollmentChallengeView.as_view(),
        name="device-enrollment-challenge",
    ),
    path("devices/enroll/", DeviceEnrollmentView.as_view(), name="device-enroll"),
    path("devices/", DeviceListView.as_view(), name="device-list"),
    path(
        "devices/<uuid:device_id>/",
        DeviceDetailView.as_view(),
        name="device-detail",
    ),
    path(
        "devices/<uuid:device_id>/approve/",
        DeviceApproveView.as_view(),
        name="device-approve",
    ),
    path(
        "devices/<uuid:device_id>/reject/",
        DeviceRejectView.as_view(),
        name="device-reject",
    ),
    path(
        "devices/<uuid:device_id>/revoke/",
        DeviceRevokeView.as_view(),
        name="device-revoke",
    ),
    path(
        "locations/zones/",
        AttendanceZoneListCreateView.as_view(),
        name="location-zone-list",
    ),
    path(
        "locations/zones/<uuid:zone_id>/",
        AttendanceZoneDetailView.as_view(),
        name="location-zone-detail",
    ),
    path(
        "locations/access-points/",
        ApprovedAccessPointListCreateView.as_view(),
        name="location-access-point-list",
    ),
    path(
        "locations/access-points/<uuid:access_point_id>/",
        ApprovedAccessPointDetailView.as_view(),
        name="location-access-point-detail",
    ),
    path("staff/", StaffListCreateView.as_view(), name="staff-list"),
    path(
        "departments/",
        DepartmentListCreateView.as_view(),
        name="department-list",
    ),
    path(
        "departments/<uuid:department_id>/",
        DepartmentDetailView.as_view(),
        name="department-detail",
    ),
    path("schedules/", WorkScheduleListCreateView.as_view(), name="schedule-list"),
    path(
        "schedules/<uuid:schedule_id>/",
        WorkScheduleDetailView.as_view(),
        name="schedule-detail",
    ),
    path(
        "schedules/<uuid:schedule_id>/versions/",
        ScheduleVersionListCreateView.as_view(),
        name="schedule-version-list",
    ),
    path(
        "schedule-assignments/",
        ScheduleAssignmentListCreateView.as_view(),
        name="schedule-assignment-list",
    ),
    path(
        "schedule-assignments/<uuid:assignment_id>/",
        ScheduleAssignmentDetailView.as_view(),
        name="schedule-assignment-detail",
    ),
    path(
        "schedule-exceptions/",
        ScheduleExceptionListCreateView.as_view(),
        name="schedule-exception-list",
    ),
    path(
        "schedule-exceptions/<uuid:exception_id>/",
        ScheduleExceptionDetailView.as_view(),
        name="schedule-exception-detail",
    ),
    path(
        "calendar-events/",
        SchoolCalendarEventListCreateView.as_view(),
        name="calendar-event-list",
    ),
    path(
        "calendar-events/<uuid:event_id>/",
        SchoolCalendarEventDetailView.as_view(),
        name="calendar-event-detail",
    ),
    path("leave-types/", LeaveTypeListCreateView.as_view(), name="leave-type-list"),
    path(
        "leave-types/<uuid:leave_type_id>/",
        LeaveTypeDetailView.as_view(),
        name="leave-type-detail",
    ),
    path("leave-records/", LeaveRecordListCreateView.as_view(), name="leave-record-list"),
    path(
        "leave-records/<uuid:leave_id>/review/",
        LeaveRecordReviewView.as_view(),
        name="leave-record-review",
    ),
    path(
        "leave-records/<uuid:leave_id>/cancel/",
        LeaveRecordCancelView.as_view(),
        name="leave-record-cancel",
    ),
    path(
        "staff/<uuid:staff_id>/",
        StaffDetailView.as_view(),
        name="staff-detail",
    ),
]
