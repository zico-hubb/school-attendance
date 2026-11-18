from datetime import date, time

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from leave_management.models import SchoolCalendarEvent
from scheduling.models import (
    ScheduleAssignment,
    ScheduleDay,
    ScheduleException,
    ScheduleVersion,
    WorkSchedule,
)
from scheduling.services import schedule_for_date
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


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def schedule_days(start="08:00", end="16:00", late="08:15", absence="10:00"):
    return [
        {
            "weekday": weekday,
            "is_working_day": weekday < 5,
            "start_time": start if weekday < 5 else None,
            "end_time": end if weekday < 5 else None,
            "late_after": late if weekday < 5 else None,
            "absence_finalization_time": absence if weekday < 5 else None,
        }
        for weekday in range(7)
    ]


def url(name, **kwargs):
    return reverse(f"api:{name}", kwargs={"version": "1", **kwargs})


def make_schedule(school, admin, name, effective_from, start=time(8)):
    schedule = WorkSchedule.objects.create(school=school, name=name)
    version = ScheduleVersion.objects.create(
        school=school,
        work_schedule=schedule,
        version_number=1,
        effective_from=effective_from,
        created_by=admin,
    )
    for weekday in range(7):
        working = weekday < 5
        ScheduleDay.objects.create(
            school=school,
            schedule_version=version,
            weekday=weekday,
            is_working_day=working,
            start_time=start if working else None,
            end_time=time(16) if working else None,
            late_after=time(8, 15) if working else None,
            absence_finalization_time=time(10) if working else None,
        )
    version.activate()
    return schedule


def make_staff(school, username, department=None):
    user = make_user(school, username, User.Role.STAFF)
    return StaffProfile.objects.create(
        school=school,
        user=user,
        employee_number=username.upper(),
        first_name=username.title(),
        last_name="Teacher",
        department=department,
        date_joined=date(2020, 1, 1),
    )


def test_admin_creates_versioned_schedule_and_manager_is_read_only():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    manager = make_user(school, "manager", User.Role.ATTENDANCE_MANAGER)
    client = authenticated_client(admin)
    payload = {
        "name": "Standard",
        "description": "Teaching staff",
        "effective_from": "2025-01-01",
        "days": schedule_days(),
    }

    created = client.post(url("schedule-list"), payload, format="json")

    assert created.status_code == 201, created.data
    result = created.json()
    assert result["versions"][0]["is_active"] is True
    assert len(result["versions"][0]["days"]) == 7
    assert ScheduleVersion.objects.filter(
        work_schedule__school=school, is_active=True
    ).count() == 1
    assert AuditLog.objects.filter(action="WORK_SCHEDULE_CREATED").count() == 1

    manager_client = authenticated_client(manager)
    assert manager_client.get(url("schedule-list")).status_code == 200
    assert manager_client.post(url("schedule-list"), payload, format="json").status_code == 403
    assert manager_client.patch(
        url("schedule-detail", schedule_id=result["id"]),
        {"is_active": False},
        format="json",
    ).status_code == 403


def test_schedule_creation_rejects_missing_weekdays_and_unknown_fields():
    school = make_school("NORTH")
    client = authenticated_client(make_user(school, "admin", User.Role.SCHOOL_ADMIN))
    payload = {
        "name": "Standard",
        "effective_from": "2025-01-01",
        "days": schedule_days()[:-1],
    }
    assert client.post(url("schedule-list"), payload, format="json").status_code == 400
    payload["days"] = schedule_days()
    payload["school"] = str(school.pk)
    assert client.post(url("schedule-list"), payload, format="json").status_code == 400
    assert WorkSchedule.objects.count() == 0


def test_new_schedule_version_closes_prior_open_range():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    created = client.post(
        url("schedule-list"),
        {
            "name": "Standard",
            "effective_from": "2025-01-01",
            "days": schedule_days(),
        },
        format="json",
    )
    assert created.status_code == 201, created.data

    updated = client.post(
        url("schedule-version-list", schedule_id=created.json()["id"]),
        {"effective_from": "2025-02-01", "days": schedule_days(start="09:00")},
        format="json",
    )

    assert updated.status_code == 201, updated.data
    versions = updated.json()["versions"]
    first = next(item for item in versions if item["version_number"] == 1)
    second = next(item for item in versions if item["version_number"] == 2)
    assert first["effective_to"] == "2025-01-31"
    assert second["effective_from"] == "2025-02-01"
    assert second["days"][0]["start_time"] == "09:00:00"


def test_assignment_precedence_is_staff_then_department_then_school_default():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    department = Department.objects.create(school=school, name="Science")
    staff = make_staff(school, "ada", department)
    target_date = date(2025, 1, 6)
    default_schedule = make_schedule(school, admin, "Default", target_date)
    department_schedule = make_schedule(
        school, admin, "Department", target_date, time(9)
    )
    staff_schedule = make_schedule(
        school, admin, "Staff", target_date, time(10)
    )
    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=default_schedule,
        is_school_default=True,
        effective_from=target_date,
        assigned_by=admin,
    )
    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=department_schedule,
        department=department,
        effective_from=target_date,
        assigned_by=admin,
    )

    resolved = schedule_for_date(staff, target_date)
    assert resolved["source"] == "DEPARTMENT"
    assert resolved["start_time"] == time(9)

    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=staff_schedule,
        staff_profile=staff,
        effective_from=target_date,
        assigned_by=admin,
    )
    resolved = schedule_for_date(staff, target_date)
    assert resolved["source"] == "STAFF"
    assert resolved["start_time"] == time(10)

    exception = ScheduleException.objects.create(
        school=school,
        staff_profile=staff,
        exception_date=target_date,
        is_working_day=True,
        start_time=time(11),
        created_by=admin,
    )
    resolved = schedule_for_date(staff, target_date)
    assert resolved["source"] == "EXCEPTION"
    assert resolved["exception"] == exception
    assert resolved["start_time"] == time(11)
    assert resolved["end_time"] == time(16)
    assert resolved["absence_finalization_time"] == time(10)


def test_schedule_default_assignment_requires_single_nonoverlapping_default():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    schedule = make_schedule(school, admin, "Default", date(2025, 1, 1))
    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=schedule,
        is_school_default=True,
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 1, 31),
        assigned_by=admin,
    )

    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        ScheduleAssignment.objects.create(
            school=school,
            work_schedule=schedule,
            is_school_default=True,
            effective_from=date(2025, 1, 31),
            assigned_by=admin,
        )


def test_calendar_event_and_staff_exception_override_weekly_schedule():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    department = Department.objects.create(school=school, name="Science")
    staff = make_staff(school, "ada", department)
    target_date = date(2025, 1, 6)
    schedule = make_schedule(school, admin, "Standard", target_date)
    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=schedule,
        is_school_default=True,
        effective_from=target_date,
        assigned_by=admin,
    )
    SchoolCalendarEvent.objects.create(
        school=school,
        name="School holiday",
        event_type=SchoolCalendarEvent.EventType.HOLIDAY,
        start_date=target_date,
        end_date=target_date,
        created_by=admin,
    )

    resolved = schedule_for_date(staff, target_date)
    assert resolved["source"] == "CALENDAR"
    assert resolved["is_working_day"] is False

    working_event = SchoolCalendarEvent.objects.create(
        school=school,
        name="Science open day",
        event_type=SchoolCalendarEvent.EventType.EXCEPTIONAL_WORKING_DAY,
        start_date=target_date,
        end_date=target_date,
        start_time=time(9),
        end_time=time(17),
        late_after=time(9, 15),
        absence_finalization_time=time(11),
        department=department,
        created_by=admin,
    )
    resolved = schedule_for_date(staff, target_date)
    assert resolved["calendar_event"] == working_event
    assert resolved["is_working_day"] is True
    assert resolved["start_time"] == time(9)
    assert resolved["absence_finalization_time"] == time(11)

    exception = ScheduleException.objects.create(
        school=school,
        staff_profile=staff,
        exception_date=target_date,
        is_working_day=False,
        created_by=admin,
    )
    resolved = schedule_for_date(staff, target_date)
    assert resolved["source"] == "EXCEPTION"
    assert resolved["exception"] == exception
    assert resolved["is_working_day"] is False
