from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from devices.models import UserSession
from schools.models import Department, School
from staff.models import StaffProfile

pytestmark = pytest.mark.django_db


def make_school(code):
    return School.objects.create(school_code=code, name=f"School {code}")


def make_user(school, username, role=User.Role.STAFF, password="School-Strong-93!"):
    return User.objects.create_user(
        username=username,
        password=password,
        school=school,
        role=role,
    )


def make_staff(school, username, employee_number):
    user = make_user(school, username)
    profile = StaffProfile.objects.create(
        school=school,
        user=user,
        employee_number=employee_number,
        first_name="Ada",
        last_name="Lovelace",
        date_joined=date(2024, 1, 1),
    )
    return user, profile


def login(client, school, username, password="School-Strong-93!"):
    return client.post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {
            "school_code": school.school_code,
            "username": username,
            "password": password,
        },
        format="json",
    )


def staff_url():
    return reverse("api:staff-list", kwargs={"version": "1"})


def detail_url(profile):
    return reverse(
        "api:staff-detail",
        kwargs={"version": "1", "staff_id": profile.pk},
    )


def test_login_issues_hashed_refresh_token_and_access_token():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = APIClient()

    response = login(client, school, "ADMIN")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["user"] == {
        "id": str(admin.pk),
        "username": "admin",
        "role": User.Role.SCHOOL_ADMIN,
        "school_code": school.school_code,
    }
    session = UserSession.objects.get(user=admin)
    assert session.refresh_token_hash != body["refresh_token"]
    assert session.device is None

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")
    assert client.get(staff_url()).status_code == 200


@pytest.mark.parametrize(
    ("school_code", "username", "password"),
    [
        ("UNKNOWN", "teacher", "School-Strong-93!"),
        ("NORTH", "missing", "School-Strong-93!"),
        ("NORTH", "teacher", "wrong-password"),
    ],
)
def test_login_returns_same_generic_error_for_invalid_credentials(
    school_code, username, password
):
    school = make_school("NORTH")
    make_user(school, "teacher")
    response = APIClient().post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {
            "school_code": school_code,
            "username": username,
            "password": password,
        },
        format="json",
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid school code, username, or password."
    }
    assert UserSession.objects.count() == 0


def test_login_requires_school_code_without_exposing_identity():
    school = make_school("NORTH")
    make_user(school, "teacher")

    response = APIClient().post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {"username": "teacher", "password": "School-Strong-93!"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "School code, username, and password are required and must be valid."
    }
    assert UserSession.objects.count() == 0


def test_identical_usernames_authenticate_only_in_the_selected_school():
    first_school = make_school("NORTH")
    second_school = make_school("SOUTH")
    make_user(first_school, "teacher", password="First-School-Password-8!")
    second_user = make_user(
        second_school, "teacher", password="Second-School-Password-8!"
    )

    response = login(
        APIClient(),
        second_school,
        "teacher",
        password="Second-School-Password-8!",
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(second_user.pk)
    assert response.json()["user"]["school_code"] == second_school.school_code


def test_inactive_accounts_are_distinguished_after_valid_password():
    school = make_school("NORTH")
    user = make_user(school, "teacher")
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = login(APIClient(), school, user.username)

    assert response.status_code == 403
    assert response.json() == {
        "state": "ACCOUNT_INACTIVE",
        "detail": "The account is inactive.",
    }
    assert UserSession.objects.count() == 0


def test_refresh_rotates_tokens_and_invalidates_the_previous_refresh_token():
    school = make_school("NORTH")
    user = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = APIClient()
    login_response = login(client, school, user.username)
    old_refresh = login_response.json()["refresh_token"]

    refresh_url = reverse("api:auth-refresh", kwargs={"version": "1"})
    refreshed = client.post(
        refresh_url, {"refresh_token": old_refresh}, format="json"
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != old_refresh
    assert UserSession.objects.get(user=user).last_used_at is not None
    assert client.post(
        refresh_url, {"refresh_token": old_refresh}, format="json"
    ).status_code == 401
    session = UserSession.objects.get(user=user)
    assert session.revoked_at is not None

    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {refreshed.json()['access_token']}"
    )
    assert client.get(staff_url()).status_code == 401


def test_expired_refresh_token_is_rejected():
    school = make_school("NORTH")
    user = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    body = login(APIClient(), school, user.username).json()
    session = UserSession.objects.get(user=user)
    session.expires_at = timezone.now() - timedelta(seconds=1)
    session.save(update_fields=["expires_at", "updated_at"])

    response = APIClient().post(
        reverse("api:auth-refresh", kwargs={"version": "1"}),
        {"refresh_token": body["refresh_token"]},
        format="json",
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired refresh token."}


def test_expired_access_token_is_rejected(settings):
    school = make_school("NORTH")
    user = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    body = login(APIClient(), school, user.username).json()
    settings.ACCESS_TOKEN_TTL_SECONDS = -1
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")

    response = client.get(staff_url())

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token."}


def test_logout_revokes_access_and_refresh_tokens():
    school = make_school("NORTH")
    user = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = APIClient()
    body = login(client, school, user.username).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access_token']}")

    logout_response = client.post(
        reverse("api:auth-logout", kwargs={"version": "1"})
    )

    assert logout_response.status_code == 204
    assert UserSession.objects.get(user=user).revoked_at is not None
    assert client.get(staff_url()).status_code == 401
    assert (
        client.post(
            reverse("api:auth-refresh", kwargs={"version": "1"}),
            {"refresh_token": body["refresh_token"]},
            format="json",
        ).status_code
        == 401
    )


def test_only_school_admins_can_manage_staff():
    school = make_school("NORTH")
    assert APIClient().post(staff_url(), {}, format="json").status_code == 401

    for role in (User.Role.STAFF, User.Role.ATTENDANCE_MANAGER):
        user = make_user(school, role.lower(), role)
        client = APIClient()
        client.force_authenticate(user=user)

        assert client.get(staff_url()).status_code == 403
        assert client.post(staff_url(), {}, format="json").status_code == 403


def test_school_admin_creates_staff_account_in_own_school():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    department = Department.objects.create(school=school, name="Science")
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.post(
        staff_url(),
        {
            "username": "new.teacher",
            "password": "Teacher-Account-Strong-91!",
            "email": "teacher@example.test",
            "phone": "+254700000001",
            "employee_number": "EMP-100",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "department": str(department.pk),
            "job_title": "Teacher",
            "date_joined": "2025-01-02",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    user = User.objects.get(pk=data["user_id"])
    profile = StaffProfile.objects.get(pk=data["id"])
    assert user.school_id == school.pk
    assert user.role == User.Role.STAFF
    assert user.is_staff is False
    assert user.check_password("Teacher-Account-Strong-91!")
    assert profile.school_id == school.pk
    assert profile.department_id == department.pk
    assert data["username"] == "new.teacher"
    assert "password" not in data
    assert "school_id" not in data


def test_staff_creation_rejects_client_supplied_school_id():
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.post(
        staff_url(),
        {
            "school_id": str(other_school.pk),
            "username": "teacher",
            "password": "Teacher-Account-Strong-91!",
            "employee_number": "EMP-1",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "date_joined": "2025-01-02",
        },
        format="json",
    )

    assert response.status_code == 400
    assert StaffProfile.objects.count() == 0
    assert User.objects.filter(username="teacher").count() == 0


def test_admin_can_update_staff_fields_and_deactivate_account():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    staff_user, profile = make_staff(school, "teacher", "EMP-1")
    staff_tokens = login(APIClient(), school, staff_user.username).json()
    staff_client = APIClient()
    staff_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {staff_tokens['access_token']}"
    )
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.patch(
        detail_url(profile),
        {
            "first_name": "Grace",
            "email": "grace@example.test",
            "is_active": False,
        },
        format="json",
    )

    assert response.status_code == 200
    staff_user.refresh_from_db()
    profile.refresh_from_db()
    assert profile.first_name == "Grace"
    assert staff_user.email == "grace@example.test"
    assert staff_user.is_active is False
    assert response.json()["is_active"] is False
    assert staff_client.get(staff_url()).status_code == 401
    assert (
        staff_client.post(
            reverse("api:auth-refresh", kwargs={"version": "1"}),
            {"refresh_token": staff_tokens["refresh_token"]},
            format="json",
        ).status_code
        == 401
    )
    assert client.delete(detail_url(profile)).status_code == 405
    assert StaffProfile.objects.filter(pk=profile.pk).exists()


def test_staff_apis_hide_other_schools_users_and_profiles():
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    _, local_profile = make_staff(school, "local", "EMP-1")
    foreign_user, foreign_profile = make_staff(other_school, "foreign", "EMP-1")
    client = APIClient()
    client.force_authenticate(user=admin)

    listing = client.get(staff_url(), {"user_id": str(foreign_user.pk)})

    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [str(local_profile.pk)]
    assert client.get(detail_url(foreign_profile)).status_code == 404
    assert client.patch(
        detail_url(foreign_profile), {"first_name": "Changed"}, format="json"
    ).status_code == 404
    assert client.get(
        reverse(
            "api:staff-detail",
            kwargs={"version": "1", "staff_id": foreign_user.pk},
        )
    ).status_code == 404
    assert client.get(f"/api/v1/users/{foreign_user.pk}/").status_code == 404
