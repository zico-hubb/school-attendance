from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from audit.models import AuditLog
from locations.models import ApprovedAccessPoint, AttendanceZone
from schools.models import School

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


def zone_list_url():
    return reverse("api:location-zone-list", kwargs={"version": "1"})


def zone_detail_url(zone):
    return reverse(
        "api:location-zone-detail",
        kwargs={"version": "1", "zone_id": zone.pk},
    )


def access_point_list_url():
    return reverse("api:location-access-point-list", kwargs={"version": "1"})


def access_point_detail_url(access_point):
    return reverse(
        "api:location-access-point-detail",
        kwargs={"version": "1", "access_point_id": access_point.pk},
    )


def zone_payload(name="Main Campus", **overrides):
    return {
        "name": name,
        "latitude": "-1.292066",
        "longitude": "36.821946",
        "radius_meters": 500,
        **overrides,
    }


def create_zone(client, name="Main Campus", **overrides):
    response = client.post(zone_list_url(), zone_payload(name, **overrides), format="json")
    assert response.status_code == 201, response.data
    return AttendanceZone.objects.get(pk=response.json()["id"])


def access_point_payload(zone, bssid="AA:BB:CC:DD:EE:10", name="Library AP", **overrides):
    return {
        "attendance_zone": str(zone.pk),
        "bssid": bssid,
        "name": name,
        **overrides,
    }


def create_access_point(client, zone, bssid="AA:BB:CC:DD:EE:10", **overrides):
    response = client.post(
        access_point_list_url(),
        access_point_payload(zone, bssid=bssid, **overrides),
        format="json",
    )
    assert response.status_code == 201, response.data
    return ApprovedAccessPoint.objects.get(pk=response.json()["id"])


def test_admin_creates_and_lists_only_own_attendance_zones():
    school_a = make_school("NORTH")
    school_b = make_school("SOUTH")
    admin_a = make_user(school_a, "admin-a", User.Role.SCHOOL_ADMIN)
    admin_b = make_user(school_b, "admin-b", User.Role.SCHOOL_ADMIN)
    client_a = authenticated_client(admin_a)
    zone_a = create_zone(client_a)
    zone_b = create_zone(authenticated_client(admin_b), "South Campus")

    response = client_a.get(zone_list_url())

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(zone_a.pk)]
    assert response.json()[0]["name"] == "Main Campus"
    assert response.json()[0]["latitude"] == "-1.292066"
    assert response.json()[0]["radius_meters"] == 500
    assert response.json()[0]["is_active"] is True
    assert response.json()[0]["created_at"]
    assert response.json()[0]["updated_at"]
    assert "school" not in response.json()[0]
    assert zone_b.school_id == school_b.pk


def test_admin_retrieves_updates_deactivates_and_reactivates_zone_with_audit():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    zone = create_zone(client)

    retrieved = client.get(zone_detail_url(zone))
    updated = client.patch(
        zone_detail_url(zone),
        {
            "name": "North Campus",
            "latitude": "-1.300000",
            "radius_meters": 750,
        },
        format="json",
    )
    deactivated = client.patch(
        zone_detail_url(zone), {"is_active": False}, format="json"
    )
    reactivated = client.patch(
        zone_detail_url(zone), {"is_active": True}, format="json"
    )

    assert retrieved.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["name"] == "North Campus"
    assert updated.json()["latitude"] == "-1.300000"
    assert updated.json()["radius_meters"] == 750
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    assert list(
        AuditLog.objects.filter(entity_type="AttendanceZone", entity_id=zone.pk)
        .order_by("created_at")
        .values_list("action", flat=True)
    ) == [
        "ATTENDANCE_ZONE_CREATED",
        "ATTENDANCE_ZONE_UPDATED",
        "ATTENDANCE_ZONE_DEACTIVATED",
        "ATTENDANCE_ZONE_ACTIVATED",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", "-90.000001"),
        ("latitude", "90.000001"),
        ("longitude", "-180.000001"),
        ("longitude", "180.000001"),
        ("radius_meters", 0),
        ("radius_meters", -1),
        ("radius_meters", 5001),
    ],
)
def test_invalid_zone_coordinates_and_radii_are_rejected_without_audit(field, value):
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    payload = zone_payload(**{field: value})

    response = authenticated_client(admin).post(
        zone_list_url(), payload, format="json"
    )

    assert response.status_code == 400
    assert AttendanceZone.objects.count() == 0
    assert not AuditLog.objects.filter(entity_type="AttendanceZone").exists()


def test_zone_radius_limit_is_configurable(settings):
    settings.MAX_ATTENDANCE_ZONE_RADIUS_METERS = 250
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)

    accepted = client.post(
        zone_list_url(),
        zone_payload(radius_meters=250),
        format="json",
    )
    rejected = client.post(
        zone_list_url(),
        zone_payload("Too large", radius_meters=251),
        format="json",
    )

    assert accepted.status_code == 201
    assert rejected.status_code == 400
    assert AttendanceZone.objects.count() == 1


def test_zone_creation_rejects_client_school_fields_and_duplicate_names():
    school = make_school("NORTH")
    other_school = make_school("SOUTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    created = client.post(zone_list_url(), zone_payload(), format="json")
    supplied_school = client.post(
        zone_list_url(),
        zone_payload("Other", school_id=str(other_school.pk)),
        format="json",
    )
    duplicate = client.post(zone_list_url(), zone_payload(), format="json")

    assert created.status_code == 201
    assert supplied_school.status_code == 400
    assert duplicate.status_code == 400
    assert AttendanceZone.objects.count() == 1
    assert AuditLog.objects.filter(action="ATTENDANCE_ZONE_CREATED").count() == 1


def test_foreign_school_zone_get_and_patch_return_not_found():
    school_a = make_school("NORTH")
    school_b = make_school("SOUTH")
    admin_a = make_user(school_a, "admin-a", User.Role.SCHOOL_ADMIN)
    admin_b = make_user(school_b, "admin-b", User.Role.SCHOOL_ADMIN)
    zone = create_zone(authenticated_client(admin_b), "South Campus")
    client = authenticated_client(admin_a)

    read = client.get(zone_detail_url(zone))
    update = client.patch(
        zone_detail_url(zone), {"name": "Changed"}, format="json"
    )

    zone.refresh_from_db()
    assert read.status_code == 404
    assert update.status_code == 404
    assert zone.name == "South Campus"
    assert not AuditLog.objects.filter(
        entity_type="AttendanceZone", entity_id=zone.pk, actor_user=admin_a
    ).exists()


@pytest.mark.parametrize(
    ("input_bssid", "canonical"),
    [
        ("aa:bb:cc:dd:ee:10", "AA:BB:CC:DD:EE:10"),
        ("aa-bb-cc-dd-ee-10", "AA:BB:CC:DD:EE:10"),
        ("aabb.ccdd.ee10", "AA:BB:CC:DD:EE:10"),
        ("AABBCCDDEE10", "AA:BB:CC:DD:EE:10"),
    ],
)
def test_access_point_normalizes_supported_bssid_formats(input_bssid, canonical):
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    zone = create_zone(client)

    response = client.post(
        access_point_list_url(),
        access_point_payload(zone, bssid=input_bssid),
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.json()["bssid"] == canonical
    assert ApprovedAccessPoint.objects.get(pk=response.json()["id"]).normalized_bssid == canonical
    audit = AuditLog.objects.get(
        action="ACCESS_POINT_REGISTERED",
        entity_id=response.json()["id"],
        actor_user=admin,
    )
    assert audit.school_id == school.pk
    assert audit.after_data["bssid"] == canonical
    assert audit.after_data["attendance_zone"] == str(zone.pk)


@pytest.mark.parametrize(
    "bssid",
    [
        "not-a-bssid",
        "AA:BB:CC:DD:EE",
        "AA:BB:CC:DD:EE:10:20",
        "AA:BB-CC:DD:EE:10",
        "FF:BB:CC:DD:EE:10",
        "00:00:00:00:00:00",
    ],
)
def test_malformed_bssid_is_rejected_without_audit(bssid):
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    zone = create_zone(client)

    response = client.post(
        access_point_list_url(),
        access_point_payload(zone, bssid=bssid),
        format="json",
    )

    assert response.status_code == 400
    assert ApprovedAccessPoint.objects.count() == 0
    assert not AuditLog.objects.filter(entity_type="ApprovedAccessPoint").exists()


def test_duplicate_bssid_after_normalization_is_rejected_in_same_school():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    zone = create_zone(client)
    first = client.post(
        access_point_list_url(),
        access_point_payload(zone, bssid="aa-bb-cc-dd-ee-10"),
        format="json",
    )
    second = client.post(
        access_point_list_url(),
        access_point_payload(zone, bssid="AABB.CCDD.EE10", name="Duplicate"),
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 400
    assert ApprovedAccessPoint.objects.count() == 1
    assert AuditLog.objects.filter(action="ACCESS_POINT_REGISTERED").count() == 1


def test_same_bssid_is_allowed_in_separate_schools():
    school_a = make_school("NORTH")
    school_b = make_school("SOUTH")
    admin_a = make_user(school_a, "admin-a", User.Role.SCHOOL_ADMIN)
    admin_b = make_user(school_b, "admin-b", User.Role.SCHOOL_ADMIN)
    client_a = authenticated_client(admin_a)
    client_b = authenticated_client(admin_b)
    zone_a = create_zone(client_a)
    zone_b = create_zone(client_b, "South Campus")

    first = client_a.post(
        access_point_list_url(),
        access_point_payload(zone_a),
        format="json",
    )
    second = client_b.post(
        access_point_list_url(),
        access_point_payload(zone_b),
        format="json",
    )
    list_a = client_a.get(access_point_list_url())
    list_b = client_b.get(access_point_list_url())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["bssid"] == second.json()["bssid"]
    assert ApprovedAccessPoint.objects.filter(
        normalized_bssid=first.json()["bssid"]
    ).count() == 2
    assert [item["id"] for item in list_a.json()] == [first.json()["id"]]
    assert [item["id"] for item in list_b.json()] == [second.json()["id"]]


def test_admin_updates_and_toggles_access_point_with_audit():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)
    zone = create_zone(client)
    access_point = create_access_point(client, zone)

    read = client.get(access_point_detail_url(access_point))
    updated = client.patch(
        access_point_detail_url(access_point),
        {"name": "Updated Library AP", "location_notes": "North entrance"},
        format="json",
    )
    deactivated = client.patch(
        access_point_detail_url(access_point),
        {"is_active": False},
        format="json",
    )
    reactivated = client.patch(
        access_point_detail_url(access_point),
        {"is_active": True},
        format="json",
    )
    forbidden_identity_change = client.patch(
        access_point_detail_url(access_point),
        {"bssid": "AA:BB:CC:DD:EE:20"},
        format="json",
    )

    assert read.status_code == 200
    assert read.json()["name"] == "Library AP"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Library AP"
    assert updated.json()["location_notes"] == "North entrance"
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    assert forbidden_identity_change.status_code == 400
    assert list(
        AuditLog.objects.filter(
            entity_type="ApprovedAccessPoint", entity_id=access_point.pk
        )
        .order_by("created_at")
        .values_list("action", flat=True)
    ) == [
        "ACCESS_POINT_REGISTERED",
        "ACCESS_POINT_UPDATED",
        "ACCESS_POINT_DEACTIVATED",
        "ACCESS_POINT_ACTIVATED",
    ]


def test_access_point_requires_a_zone_in_the_same_school():
    school_a = make_school("NORTH")
    school_b = make_school("SOUTH")
    admin_a = make_user(school_a, "admin-a", User.Role.SCHOOL_ADMIN)
    admin_b = make_user(school_b, "admin-b", User.Role.SCHOOL_ADMIN)
    foreign_zone = create_zone(authenticated_client(admin_b), "South Campus")
    client = authenticated_client(admin_a)

    response = client.post(
        access_point_list_url(),
        access_point_payload(foreign_zone),
        format="json",
    )

    assert response.status_code == 400
    assert ApprovedAccessPoint.objects.count() == 0
    assert not AuditLog.objects.filter(action="ACCESS_POINT_REGISTERED").exists()


def test_foreign_school_access_point_get_and_patch_return_not_found():
    school_a = make_school("NORTH")
    school_b = make_school("SOUTH")
    admin_a = make_user(school_a, "admin-a", User.Role.SCHOOL_ADMIN)
    admin_b = make_user(school_b, "admin-b", User.Role.SCHOOL_ADMIN)
    zone_b = create_zone(authenticated_client(admin_b), "South Campus")
    access_point = create_access_point(authenticated_client(admin_b), zone_b)
    client = authenticated_client(admin_a)

    read = client.get(access_point_detail_url(access_point))
    update = client.patch(
        access_point_detail_url(access_point),
        {"name": "Changed"},
        format="json",
    )

    access_point.refresh_from_db()
    assert read.status_code == 404
    assert update.status_code == 404
    assert access_point.label == "Library AP"
    assert not AuditLog.objects.filter(
        entity_type="ApprovedAccessPoint",
        entity_id=access_point.pk,
        actor_user=admin_a,
    ).exists()


@pytest.mark.parametrize(
    "path_factory",
    [zone_list_url, access_point_list_url],
)
def test_configuration_endpoints_require_authentication(path_factory):
    response = APIClient().get(path_factory())
    create_response = APIClient().post(path_factory(), {}, format="json")
    assert response.status_code == 401
    assert create_response.status_code == 401


def test_attendance_manager_can_read_but_not_mutate_configuration():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    manager = make_user(
        school, "manager", User.Role.ATTENDANCE_MANAGER
    )
    admin_api = authenticated_client(admin)
    zone = create_zone(admin_api)
    access_point = create_access_point(admin_api, zone)
    client = authenticated_client(manager)

    zone_list = client.get(zone_list_url())
    zone_create = client.post(zone_list_url(), zone_payload(), format="json")
    zone_update = client.patch(
        zone_detail_url(zone), {"name": "Unauthorized"}, format="json"
    )
    access_point_list = client.get(access_point_list_url())
    access_point_create = client.post(
        access_point_list_url(), {}, format="json"
    )
    access_point_update = client.patch(
        access_point_detail_url(access_point),
        {"name": "Unauthorized"},
        format="json",
    )

    assert zone_list.status_code == 200
    assert zone_create.status_code == 403
    assert zone_update.status_code == 403
    assert access_point_list.status_code == 200
    assert access_point_create.status_code == 403
    assert access_point_update.status_code == 403
    assert AttendanceZone.objects.count() == 1
    assert ApprovedAccessPoint.objects.count() == 1
    assert AuditLog.objects.filter(
        entity_type__in=["AttendanceZone", "ApprovedAccessPoint"]
    ).count() == 2


def test_staff_cannot_read_or_mutate_configuration():
    school = make_school("NORTH")
    staff_user = make_user(school, "staff", User.Role.STAFF)
    client = authenticated_client(staff_user)

    assert client.get(zone_list_url()).status_code == 403
    assert client.post(zone_list_url(), zone_payload(), format="json").status_code == 403
    assert client.get(access_point_list_url()).status_code == 403
    assert client.post(
        access_point_list_url(), {}, format="json"
    ).status_code == 403


@pytest.mark.parametrize(
    ("latitude", "longitude", "radius"),
    [
        (Decimal("91"), Decimal("0"), 500),
        (Decimal("0"), Decimal("-181"), 500),
        (Decimal("0"), Decimal("0"), 0),
        (Decimal("0"), Decimal("0"), 10001),
    ],
)
def test_database_constraints_reject_invalid_zone_values(
    latitude, longitude, radius
):
    school = make_school("NORTH")
    zone = AttendanceZone(
        school=school,
        name="Invalid",
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        AttendanceZone.objects.bulk_create([zone])


def test_database_enforces_school_scoped_bssid_uniqueness():
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    zone = create_zone(authenticated_client(admin))
    first = ApprovedAccessPoint(
        school=school,
        attendance_zone=zone,
        normalized_bssid="AA:BB:CC:DD:EE:10",
        label="First",
    )
    duplicate = ApprovedAccessPoint(
        school=school,
        attendance_zone=zone,
        normalized_bssid="AA:BB:CC:DD:EE:10",
        label="Duplicate",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ApprovedAccessPoint.objects.bulk_create([first, duplicate])


def test_configuration_mutation_and_audit_write_are_atomic(monkeypatch):
    school = make_school("NORTH")
    admin = make_user(school, "admin", User.Role.SCHOOL_ADMIN)
    client = authenticated_client(admin)

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(AuditLog.objects, "create", fail_audit)
    with pytest.raises(RuntimeError, match="audit storage unavailable"):
        client.post(zone_list_url(), zone_payload(), format="json")

    assert AttendanceZone.objects.count() == 0
