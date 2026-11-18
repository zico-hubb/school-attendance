import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from schools.models import Department, School


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


def department_list_url():
    return reverse("api:department-list", kwargs={"version": "1"})


def department_detail_url(department):
    return reverse(
        "api:department-detail",
        kwargs={"version": "1", "department_id": department.pk},
    )


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_admin_manages_school_departments_with_audit():
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    other_admin = make_user(other_school, "other-admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    foreign_department = Department.objects.create(
        school=other_school, name="Foreign"
    )

    created = client.post(
        department_list_url(),
        {"name": "Science", "description": "Science department"},
        format="json",
    )

    assert created.status_code == 201
    department = Department.objects.get(pk=created.json()["id"])
    assert department.school_id == school.pk
    assert created.json()["is_active"] is True
    assert "school" not in created.json()
    assert client.get(department_list_url()).json() == [created.json()]
    assert client.get(department_detail_url(foreign_department)).status_code == 404
    assert client.patch(
        department_detail_url(foreign_department),
        {"name": "Changed"},
        format="json",
    ).status_code == 404

    updated = client.patch(
        department_detail_url(department),
        {"name": "Science and Technology"},
        format="json",
    )
    deactivated = client.patch(
        department_detail_url(department), {"is_active": False}, format="json"
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == "Science and Technology"
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert list(
        AuditLog.objects.filter(entity_type="Department", school=school)
        .order_by("created_at")
        .values_list("action", flat=True)
    ) == [
        "DEPARTMENT_CREATED",
        "DEPARTMENT_UPDATED",
        "DEPARTMENT_DEACTIVATED",
    ]
    assert other_admin.school_id == foreign_department.school_id


def test_attendance_manager_can_read_but_not_mutate_departments():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    manager = make_user(school, "manager", User.Role.ATTENDANCE_MANAGER)
    department = Department.objects.create(school=school, name="Science")

    response = authenticated_client(manager).get(department_list_url())

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(department.pk)
    assert authenticated_client(manager).post(
        department_list_url(), {"name": "Arts"}, format="json"
    ).status_code == 403
    assert authenticated_client(manager).patch(
        department_detail_url(department),
        {"name": "Arts"},
        format="json",
    ).status_code == 403
    assert authenticated_client(make_user(school, "staff", User.Role.STAFF)).get(
        department_list_url()
    ).status_code == 403
    assert admin.role == User.Role.SCHOOL_ADMIN


def test_department_rejects_duplicate_and_unknown_fields():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)

    first = client.post(
        department_list_url(), {"name": "Science"}, format="json"
    )
    duplicate = client.post(
        department_list_url(), {"name": "Science"}, format="json"
    )
    forged_school = client.post(
        department_list_url(),
        {"name": "Arts", "school_id": str(make_school("SOUTH").pk)},
        format="json",
    )

    assert first.status_code == 201
    assert duplicate.status_code == 400
    assert forged_school.status_code == 400
    assert Department.objects.filter(school=school).count() == 1
