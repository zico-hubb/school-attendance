from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from schools.models import School

pytestmark = pytest.mark.django_db

PASSWORD = "Provisioned-Admin-Strong-93!"


def run_provisioning(
    monkeypatch,
    *,
    name="North School",
    code="NORTH-1",
    username="initial.admin",
    password=PASSWORD,
    confirmation=None,
    output=None,
):
    answers = iter([name, code, username])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    passwords = iter(
        [password, confirmation if confirmation is not None else password]
    )
    monkeypatch.setattr(
        "schools.management.commands.provision_school.getpass",
        lambda _prompt: next(passwords),
    )
    call_command("provision_school", stdout=output or StringIO())


def test_provisioning_creates_school_admin_and_supports_login(monkeypatch):
    output = StringIO()
    run_provisioning(monkeypatch, output=output)

    school = School.objects.get(school_code="NORTH-1")
    administrator = User.objects.get(school=school)
    assert school.name == "North School"
    assert administrator.username == "initial.admin"
    assert administrator.role == User.Role.SCHOOL_ADMIN
    assert administrator.school_id == school.pk
    assert administrator.check_password(PASSWORD)
    assert administrator.password != PASSWORD

    response = APIClient().post(
        reverse("api:auth-login", kwargs={"version": "1"}),
        {
            "school_code": school.school_code,
            "username": administrator.username,
            "password": PASSWORD,
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == User.Role.SCHOOL_ADMIN
    assert response.json()["user"]["school_code"] == school.school_code

    audit = AuditLog.objects.get(school=school, action="SCHOOL_PROVISIONED")
    assert audit.actor_user is None
    assert audit.after_data == {
        "school_code": school.school_code,
        "administrator_username": administrator.username,
    }
    assert PASSWORD not in output.getvalue()


def test_duplicate_school_code_does_not_change_existing_records(monkeypatch):
    existing = School.objects.create(school_code="NORTH-1", name="Existing School")
    output = StringIO()
    with pytest.raises(CommandError, match="already exists"):
        run_provisioning(monkeypatch, output=output)

    existing.refresh_from_db()
    assert existing.name == "Existing School"
    assert School.objects.count() == 1
    assert User.objects.count() == 0
    assert output.getvalue() == ""


@pytest.mark.parametrize(
    ("name", "code", "username", "password", "confirmation", "message"),
    [
        ("", "NORTH-1", "admin", PASSWORD, PASSWORD, "name"),
        ("North School", "", "admin", PASSWORD, PASSWORD, "school_code"),
        ("North School", "NORTH-1", "", PASSWORD, PASSWORD, "username"),
        (
            "North School",
            "NORTH-1",
            "admin",
            PASSWORD,
            "Different-Password-93!",
            "confirmation",
        ),
        (
            "North School",
            "NORTH-1",
            "admin",
            "password",
            "password",
            "password",
        ),
    ],
)
def test_invalid_inputs_are_rejected_without_creating_records(
    monkeypatch, name, code, username, password, confirmation, message
):
    with pytest.raises(CommandError, match=message):
        run_provisioning(
            monkeypatch,
            name=name,
            code=code,
            username=username,
            password=password,
            confirmation=confirmation,
        )

    assert School.objects.count() == 0
    assert User.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_duplicate_administrator_username_rolls_back_new_school(monkeypatch):
    school = School.objects.create(school_code="NORTH-1", name="North School")
    User.objects.create_user(
        username="initial.admin",
        password=PASSWORD,
        school=school,
    )

    with pytest.raises(CommandError):
        run_provisioning(monkeypatch)

    assert School.objects.count() == 1
    assert User.objects.count() == 1
    assert not AuditLog.objects.filter(action="SCHOOL_PROVISIONED").exists()


def test_administrator_creation_failure_rolls_back_school_and_audit(
    monkeypatch,
):
    def fail_creation(*args, **kwargs):
        raise RuntimeError("administrator creation failed")

    monkeypatch.setattr(User.objects, "create_user", fail_creation)

    with pytest.raises(RuntimeError, match="administrator creation failed"):
        run_provisioning(monkeypatch)

    assert School.objects.count() == 0
    assert User.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_password_is_never_written_to_output_or_audit(monkeypatch):
    output = StringIO()
    run_provisioning(monkeypatch, output=output)

    assert PASSWORD not in output.getvalue()
    assert PASSWORD not in str(AuditLog.objects.get().after_data)
    assert PASSWORD not in str(AuditLog.objects.get().reason)
