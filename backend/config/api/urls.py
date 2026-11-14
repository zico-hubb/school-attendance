from django.urls import path

from .auth_views import LoginView, LogoutView, RefreshView
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
from .staff_views import StaffDetailView, StaffListCreateView
from .views import health

app_name = "api"

urlpatterns = [
    path("health/", health, name="health"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
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
        "staff/<uuid:staff_id>/",
        StaffDetailView.as_view(),
        name="staff-detail",
    ),
]
