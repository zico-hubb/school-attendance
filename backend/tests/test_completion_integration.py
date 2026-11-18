from datetime import date

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from attendance.models import AttendanceRecord
from audit.models import AuditLog
from schools.models import Department, School
from staff.models import StaffProfile


pytestmark = pytest.mark.django_db


def login(client, school, username, password):
    response = client.post(
        "/api/v1/auth/login/",
        {
            "school_code": school.school_code,
            "username": username,
            "password": password,
        },
        format="json",
    )
    assert response.status_code == 200
    return response.data["access_token"]


def auth(client, token):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_cross_tenant_overview_report_audit_and_settings_are_isolated():
    school_a = School.objects.create(
        school_code="INT-A",
        name="Integration A",
        timezone="Africa/Nairobi",
    )
    school_b = School.objects.create(
        school_code="INT-B",
        name="Integration B",
        timezone="Africa/Nairobi",
    )
    admin_a = User.objects.create_user(
        school=school_a,
        username="admin-a",
        password="Strong-Admin-A1!",
        role=User.Role.SCHOOL_ADMIN,
    )
    admin_b = User.objects.create_user(
        school=school_b,
        username="admin-b",
        password="Strong-Admin-B1!",
        role=User.Role.SCHOOL_ADMIN,
    )

    StaffProfile.objects.create(
        school=school_a,
        user=User.objects.create_user(
            school=school_a,
            username="staff-a",
            password="Staff-A1!",
            role=User.Role.STAFF,
        ),
        employee_number="EMP-A",
        first_name="Ada",
        last_name="A",
        date_joined=date(2025, 1, 1),
    )
    StaffProfile.objects.create(
        school=school_b,
        user=User.objects.create_user(
            school=school_b,
            username="staff-b",
            password="Staff-B1!",
            role=User.Role.STAFF,
        ),
        employee_number="EMP-B",
        first_name="Grace",
        last_name="B",
        date_joined=date(2025, 1, 1),
    )

    AuditLog.objects.create(
        school=school_a,
        actor_user=admin_a,
        action="TENANT_A_ACTION",
        entity_type="School",
        entity_id=school_a.pk,
        after_data={"tenant": "A"},
    )
    AuditLog.objects.create(
        school=school_b,
        actor_user=admin_b,
        action="TENANT_B_ACTION",
        entity_type="School",
        entity_id=school_b.pk,
        after_data={"tenant": "B"},
    )

    client = auth(APIClient(), login(APIClient(), school_a, "admin-a", "Strong-Admin-A1!"))
    overview = client.get("/api/v1/overview/")
    assert overview.status_code == 200
    assert overview.data["school"]["school_code"] == "INT-A"
    assert overview.data["staff"]["total"] == 1

    audit = client.get("/api/v1/audit-logs/")
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.data["results"]}
    assert "TENANT_A_ACTION" in actions
    assert "TENANT_B_ACTION" not in actions

    report = client.get(
        "/api/v1/reports/attendance/",
        {"date_from": "2025-01-01", "date_to": "2025-12-31"},
    )
    assert report.status_code == 200
    assert report.data["date_from"] == "2025-01-01"

    settings = client.patch(
        "/api/v1/school-settings/",
        {"timezone": "UTC", "name": "Integration A Updated"},
        format="json",
    )
    assert settings.status_code == 200
    assert settings.data["timezone"] == "UTC"
    assert settings.data["name"] == "Integration A Updated"

    client_b = auth(APIClient(), login(APIClient(), school_b, "admin-b", "Strong-Admin-B1!"))
    assert client_b.get("/api/v1/overview/").data["school"]["school_code"] == "INT-B"
    school_b_audit = client_b.get("/api/v1/audit-logs/")
    assert "TENANT_B_ACTION" in {
        entry["action"] for entry in school_b_audit.data["results"]
    }
    assert "TENANT_A_ACTION" not in {
        entry["action"] for entry in school_b_audit.data["results"]
    }


def test_attendance_manager_is_read_only_and_staff_cannot_access_dashboard_endpoints():
    school = School.objects.create(school_code="ROLE-A", name="Role School")
    manager = User.objects.create_user(
        school=school,
        username="manager",
        password="Manager-A1!",
        role=User.Role.ATTENDANCE_MANAGER,
    )
    staff = User.objects.create_user(
        school=school,
        username="staff",
        password="Staff-A1!",
        role=User.Role.STAFF,
    )
    StaffProfile.objects.create(
        school=school,
        user=staff,
        employee_number="EMP-ROLE",
        first_name="Staff",
        last_name="Member",
        date_joined=date(2025, 1, 1),
    )

    manager_client = auth(
        APIClient(),
        login(APIClient(), school, "manager", "Manager-A1!"),
    )
    assert manager_client.get("/api/v1/attendance/register/").status_code == 200
    assert manager_client.get("/api/v1/overview/").status_code == 200
    assert manager_client.post(
        "/api/v1/staff/",
        {},
        format="json",
    ).status_code == 403

    staff_client = auth(
        APIClient(),
        login(APIClient(), school, "staff", "Staff-A1!"),
    )
    assert staff_client.get("/api/v1/attendance/register/").status_code == 403
    assert staff_client.get("/api/v1/overview/").status_code == 403
    assert staff_client.get("/api/v1/audit-logs/").status_code == 403
