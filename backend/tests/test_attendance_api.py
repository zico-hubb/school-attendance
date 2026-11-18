from datetime import date, time
from decimal import Decimal

import pytest
from django.utils import timezone

from attendance.models import AttendanceAttempt
from locations.models import AttendanceZone
from schools.models import School

from config.api.attendance_views import evidence_for_request, distance_meters
from staff.models import StaffProfile
from accounts.models import User


pytestmark = pytest.mark.django_db


def test_distance_meters_and_attendance_zone_evidence():
    school = School.objects.create(school_code="ATT-1", name="Attendance School")
    user = User.objects.create_user(
        school=school,
        username="staff",
        password="test-password",
        role=User.Role.STAFF,
    )
    profile = StaffProfile.objects.create(
        school=school,
        user=user,
        employee_number="EMP-A1",
        first_name="Ada",
        last_name="Lovelace",
        date_joined=date(2025, 1, 1),
    )
    AttendanceZone.objects.create(
        school=school,
        name="Main Campus",
        latitude=Decimal("-1.286389"),
        longitude=Decimal("36.817223"),
        radius_meters=150,
        is_active=True,
    )

    assert distance_meters(-1.286389, 36.817223, -1.286389, 36.817223) < 1
    reason, detail = evidence_for_request(
        type("Request", (), {"META": {"REMOTE_ADDR": "127.0.0.1"}}),
        profile,
        timezone.now(),
        Decimal("-1.286389"),
        Decimal("36.817223"),
        Decimal("10"),
        "",
    )
    assert reason == "LOCATION_VERIFIED"
    assert "zone" in detail.lower()
