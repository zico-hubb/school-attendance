from datetime import date

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from leave_management.models import LeaveRecord, LeaveType, SchoolCalendarEvent
from schools.models import Department, School
from staff.models import StaffProfile


pytestmark = pytest.mark.django_db


def make_school(code):
    return School.objects.create(school_code=code, name=f"School {code}")


def make_user(school, username, role):
    return User.objects.create_user(
        username=username,
        password="School-Strong-93!",
        school=school,
        role=role,
    )


def make_staff(school, username):
    user = make_user(school, username, User.Role.STAFF)
    profile = StaffProfile.objects.create(
        school=school,
        user=user,
        employee_number=username.upper(),
        first_name=username.title(),
        last_name="Teacher",
        date_joined=date(2020, 1, 1),
    )
    return user, profile


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def url(name, **kwargs):
    return reverse(f"api:{name}", kwargs={"version": "1", **kwargs})


def test_staff_submits_own_leave_and_admin_reviews_with_audit():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    staff_user, profile = make_staff(school, "ada")
    leave_type = LeaveType.objects.create(school=school, name="Annual")
    staff_client = authenticated_client(staff_user)

    created = staff_client.post(
        url("leave-record-list"),
        {
            "leave_type": str(leave_type.pk),
            "start_date": "2025-03-03",
            "end_date": "2025-03-07",
            "reason": "Family leave",
        },
        format="json",
    )

    assert created.status_code == 201, created.data
    record = LeaveRecord.objects.get(pk=created.json()["id"])
    assert record.staff_profile_id == profile.pk
    assert record.status == LeaveRecord.Status.PENDING
    assert staff_client.get(url("leave-record-list")).json() == [created.json()]
    forged = staff_client.post(
        url("leave-record-list"),
        {
            "leave_type": str(leave_type.pk),
            "start_date": "2025-03-03",
            "end_date": "2025-03-07",
            "staff_profile": str(profile.pk),
        },
        format="json",
    )
    assert forged.status_code == 400

    reviewed = authenticated_client(admin).post(
        url("leave-record-review", leave_id=record.pk),
        {"status": "APPROVED", "review_comment": "Approved"},
        format="json",
    )

    assert reviewed.status_code == 200, reviewed.data
    record.refresh_from_db()
    assert record.status == LeaveRecord.Status.APPROVED
    assert record.reviewed_by_id == admin.pk
    assert record.review_comment == "Approved"
    assert AuditLog.objects.filter(action="LEAVE_REQUEST_SUBMITTED").count() == 1
    assert AuditLog.objects.filter(
        action="LEAVE_REQUEST_REVIEWED", reason="Approved"
    ).count() == 1
    assert authenticated_client(admin).get(url("leave-record-list")).json()[0][
        "staff_profile"
    ] == str(profile.pk)


def test_only_admin_reviews_and_approved_leave_cannot_overlap():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    manager = make_user(school, "manager", User.Role.ATTENDANCE_MANAGER)
    staff_user, _ = make_staff(school, "ada")
    leave_type = LeaveType.objects.create(school=school, name="Annual")
    staff_client = authenticated_client(staff_user)
    first = staff_client.post(
        url("leave-record-list"),
        {
            "leave_type": str(leave_type.pk),
            "start_date": "2025-03-03",
            "end_date": "2025-03-07",
        },
        format="json",
    )
    second = staff_client.post(
        url("leave-record-list"),
        {
            "leave_type": str(leave_type.pk),
            "start_date": "2025-03-05",
            "end_date": "2025-03-10",
        },
        format="json",
    )
    assert first.status_code == 201
    assert second.status_code == 201

    review_url = url("leave-record-review", leave_id=first.json()["id"])
    assert authenticated_client(manager).post(
        review_url, {"status": "APPROVED"}, format="json"
    ).status_code == 403
    assert authenticated_client(admin).post(
        review_url, {"status": "APPROVED"}, format="json"
    ).status_code == 200
    overlapping_review = authenticated_client(admin).post(
        url("leave-record-review", leave_id=second.json()["id"]),
        {"status": "APPROVED"},
        format="json",
    )
    assert overlapping_review.status_code == 400
    assert LeaveRecord.objects.get(pk=second.json()["id"]).status == "PENDING"


def test_staff_can_cancel_own_pending_leave_but_not_approved_leave():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    staff_user, _ = make_staff(school, "ada")
    leave_type = LeaveType.objects.create(school=school, name="Annual")
    client = authenticated_client(staff_user)
    created = client.post(
        url("leave-record-list"),
        {
            "leave_type": str(leave_type.pk),
            "start_date": "2025-04-01",
            "end_date": "2025-04-02",
        },
        format="json",
    )
    leave_id = created.json()["id"]

    cancelled = client.post(
        url("leave-record-cancel", leave_id=leave_id),
        {"cancellation_reason": "Plans changed"},
        format="json",
    )
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancellation_reason"] == "Plans changed"

    approved = client.post(
        url("leave-record-list"),
        {
            "leave_type": str(leave_type.pk),
            "start_date": "2025-04-10",
            "end_date": "2025-04-11",
        },
        format="json",
    )
    assert authenticated_client(admin).post(
        url("leave-record-review", leave_id=approved.json()["id"]),
        {"status": "APPROVED"},
        format="json",
    ).status_code == 200
    assert client.post(
        url("leave-record-cancel", leave_id=approved.json()["id"]),
        {"cancellation_reason": "Too late"},
        format="json",
    ).status_code == 400


def test_leave_types_and_calendar_events_are_tenant_scoped_and_admin_managed():
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    other_admin = make_user(other_school, "other-admin", User.Role.SCHOOL_ADMIN)
    manager = make_user(school, "manager", User.Role.ATTENDANCE_MANAGER)
    staff_user, _ = make_staff(school, "teacher")
    department = Department.objects.create(school=school, name="Science")
    client = authenticated_client(admin)
    leave_type_response = client.post(
        url("leave-type-list"),
        {"name": "Annual", "description": "Annual leave"},
        format="json",
    )
    assert leave_type_response.status_code == 201
    assert authenticated_client(other_admin).get(url("leave-type-list")).json() == []
    LeaveType.objects.create(
        school=school, name="Inactive", is_active=False
    )
    assert [
        item["name"]
        for item in authenticated_client(staff_user).get(url("leave-type-list")).json()
    ] == ["Annual"]
    assert authenticated_client(manager).post(
        url("leave-type-list"), {"name": "Sick"}, format="json"
    ).status_code == 403

    event = client.post(
        url("calendar-event-list"),
        {
            "name": "School closure",
            "event_type": SchoolCalendarEvent.EventType.CLOSURE,
            "start_date": "2025-12-24",
            "end_date": "2025-12-26",
            "department": str(department.pk),
        },
        format="json",
    )
    assert event.status_code == 201, event.data
    assert authenticated_client(manager).get(url("calendar-event-list")).json() == [
        event.json()
    ]
    assert authenticated_client(manager).patch(
        url("calendar-event-detail", event_id=event.json()["id"]),
        {"name": "Changed"},
        format="json",
    ).status_code == 403
    assert authenticated_client(other_admin).get(url("calendar-event-list")).json() == []
