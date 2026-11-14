from datetime import date, time
from decimal import Decimal
import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from accounts.models import User
from attendance.models import (
    AttendanceAttempt,
    AttendanceEvent,
    AttendanceRecord,
)
from devices.models import DeviceKey, DeviceEvent, RegisteredDevice
from leave_management.models import LeaveRecord, LeaveType
from scheduling.models import (
    ScheduleAssignment,
    ScheduleDay,
    ScheduleException,
    ScheduleVersion,
    WorkSchedule,
)
from schools.models import Department, School
from staff.models import StaffProfile

pytestmark = pytest.mark.django_db


def make_school(code="SCH-1"):
    return School.objects.create(school_code=code, name=f"School {code}")


def make_user(school, username="admin"):
    return User.objects.create_user(
        username=username, password="secure-test-password", school=school
    )


def make_staff(school, username="staff", employee_number="EMP-1", department=None):
    user = make_user(school, username)
    return StaffProfile.objects.create(
        school=school,
        user=user,
        employee_number=employee_number,
        first_name="Ada",
        last_name="Lovelace",
        department=department,
        date_joined=date(2024, 1, 1),
    )


def make_device(school, staff_profile, status=RegisteredDevice.Status.ACTIVE):
    return RegisteredDevice.objects.create(
        school=school,
        staff_profile=staff_profile,
        platform=RegisteredDevice.Platform.ANDROID,
        device_name="Staff phone",
        status=status,
        enrolled_at=timezone.now(),
    )


def make_attempt(school, staff_profile, device, attempt_type, token):
    return AttendanceAttempt.objects.create(
        school=school,
        staff_profile=staff_profile,
        device=device,
        attempt_type=attempt_type,
        attendance_date=date(2025, 6, 2),
        client_occurred_at=timezone.now(),
        latitude=Decimal("-1.286389"),
        longitude=Decimal("36.817223"),
        location_accuracy=Decimal("12.5"),
        idempotency_key=token,
        verification_result=AttendanceAttempt.VerificationResult.ACCEPTED,
    )


def test_school_code_is_unique_and_immutable():
    school = make_school()

    with pytest.raises(ValidationError):
        make_school()

    school.school_code = "SCH-2"
    with pytest.raises(ValidationError):
        school.save()


def test_username_is_normalized_and_unique_per_school_only():
    school = make_school()
    User.objects.create_user(
        username=" Admin ", password="x", school=school
    )

    with pytest.raises(ValidationError):
        User.objects.create_user(username="ADMIN", password="x", school=school)

    other_school = make_school("SCH-2")
    other_user = User.objects.create_user(
        username="ADMIN",
        password="x",
        school=other_school,
        email="shared@example.test",
        phone="+254700000000",
    )
    assert other_user.username == "admin"
    duplicate_contact = User.objects.create_user(
        username="another",
        password="x",
        school=school,
        email="shared@example.test",
        phone="+254700000000",
    )
    assert duplicate_contact.email == other_user.email


def test_school_code_authentication_is_scoped_and_checks_password():
    school = make_school()
    user = make_user(school, "Teacher")

    assert authenticate(
        school_code=school.school_code,
        username="TEACHER",
        password="secure-test-password",
    ) == user
    assert authenticate(
        school_code="OTHER",
        username="teacher",
        password="secure-test-password",
    ) is None
    assert authenticate(
        school_code=school.school_code,
        username="teacher",
        password="incorrect",
    ) is None


def test_staff_employee_number_is_unique_per_school_and_user_is_one_to_one():
    school = make_school()
    make_staff(school)

    with pytest.raises(ValidationError):
        make_staff(school, username="another", employee_number="EMP-1")

    other_school = make_school("SCH-2")
    assert make_staff(other_school, employee_number="EMP-1")

    user = make_user(school, "unprofiled")
    profile = StaffProfile(
        school=school,
        user=user,
        employee_number="EMP-2",
        first_name="Grace",
        last_name="Hopper",
        date_joined=date(2024, 1, 1),
    )
    profile.save()
    with pytest.raises(ValidationError):
        StaffProfile.objects.create(
            school=school,
            user=user,
            employee_number="EMP-3",
            first_name="Grace",
            last_name="Hopper",
            date_joined=date(2024, 1, 1),
        )


def test_only_one_active_device_per_staff_profile():
    school = make_school()
    staff_profile = make_staff(school)
    make_device(school, staff_profile)

    with pytest.raises(ValidationError):
        make_device(school, staff_profile)


def test_only_one_active_key_per_device_and_fingerprint_is_unique():
    school = make_school()
    device = make_device(school, make_staff(school))
    fields = {
        "school": school,
        "device": device,
        "public_key": "public-only",
        "algorithm": "ECDSA_P256_SHA256",
        "fingerprint": "fingerprint-one",
        "key_version": 1,
        "status": DeviceKey.Status.ACTIVE,
    }
    DeviceKey.objects.create(**fields)

    with pytest.raises(ValidationError):
        DeviceKey.objects.create(
            **{**fields, "fingerprint": "fingerprint-two", "key_version": 2}
        )
    with pytest.raises(ValidationError):
        DeviceKey.objects.create(
            **{
                **fields,
                "device": make_device(school, make_staff(school)),
                "fingerprint": "fingerprint-three",
                "key_version": 1,
            }
        )


def test_schedule_day_is_unique_per_weekday_and_activation_needs_all_days():
    school = make_school()
    admin = make_user(school)
    schedule = WorkSchedule.objects.create(school=school, name="Standard")
    version = ScheduleVersion.objects.create(
        school=school,
        work_schedule=schedule,
        version_number=1,
        effective_from=date(2025, 1, 1),
        created_by=admin,
    )
    ScheduleDay.objects.create(
        school=school,
        schedule_version=version,
        weekday=0,
        start_time=time(8),
        end_time=time(16),
    )
    with pytest.raises(ValidationError):
        ScheduleDay.objects.create(
            school=school, schedule_version=version, weekday=0
        )
    with pytest.raises(ValidationError):
        version.activate()
    for weekday in range(1, 7):
        ScheduleDay.objects.create(
            school=school,
            schedule_version=version,
            weekday=weekday,
            is_working_day=weekday < 5,
            start_time=time(8) if weekday < 5 else None,
            end_time=time(16) if weekday < 5 else None,
        )
    version.activate()
    assert ScheduleVersion.objects.get(pk=version.pk).is_active


def test_schedule_version_ranges_cannot_overlap():
    school = make_school()
    admin = make_user(school)
    schedule = WorkSchedule.objects.create(school=school, name="Standard")
    ScheduleVersion.objects.create(
        school=school,
        work_schedule=schedule,
        version_number=1,
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 1, 31),
        created_by=admin,
    )
    with pytest.raises(ValidationError):
        ScheduleVersion.objects.create(
            school=school,
            work_schedule=schedule,
            version_number=2,
            effective_from=date(2025, 1, 31),
            created_by=admin,
        )


def test_schedule_assignment_requires_one_target_and_rejects_overlaps():
    school = make_school()
    admin = make_user(school)
    department = Department.objects.create(school=school, name="Science")
    staff_profile = make_staff(
        school, username="staff", employee_number="EMP-1", department=department
    )
    schedule = WorkSchedule.objects.create(school=school, name="Standard")
    start = date(2025, 1, 1)

    with pytest.raises(ValidationError):
        ScheduleAssignment.objects.create(
            school=school,
            work_schedule=schedule,
            effective_from=start,
            assigned_by=admin,
        )
    with pytest.raises(ValidationError):
        ScheduleAssignment.objects.create(
            school=school,
            work_schedule=schedule,
            department=department,
            staff_profile=staff_profile,
            effective_from=start,
            assigned_by=admin,
        )
    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=schedule,
        department=department,
        effective_from=start,
        effective_to=date(2025, 1, 31),
        assigned_by=admin,
    )
    with pytest.raises(ValidationError):
        ScheduleAssignment.objects.create(
            school=school,
            work_schedule=schedule,
            department=department,
            effective_from=date(2025, 1, 31),
            assigned_by=admin,
        )
    ScheduleAssignment.objects.create(
        school=school,
        work_schedule=schedule,
        staff_profile=staff_profile,
        effective_from=start,
        assigned_by=admin,
    )


def test_schedule_exception_is_unique_per_staff_member_and_date():
    school = make_school()
    staff_profile = make_staff(school)
    admin = make_user(school)
    exception = {
        "school": school,
        "staff_profile": staff_profile,
        "exception_date": date(2025, 2, 1),
        "created_by": admin,
    }
    ScheduleException.objects.create(**exception)

    with pytest.raises(ValidationError):
        ScheduleException.objects.create(**exception)


def test_leave_dates_and_approved_leave_overlap_are_validated():
    school = make_school()
    staff_profile = make_staff(school)
    admin = make_user(school)
    leave_type = LeaveType.objects.create(school=school, name="Annual")
    with pytest.raises(ValidationError):
        LeaveRecord.objects.create(
            school=school,
            staff_profile=staff_profile,
            leave_type=leave_type,
            start_date=date(2025, 2, 3),
            end_date=date(2025, 2, 2),
        )

    review_time = timezone.now()
    leave_fields = {
        "school": school,
        "staff_profile": staff_profile,
        "leave_type": leave_type,
        "start_date": date(2025, 2, 3),
        "end_date": date(2025, 2, 7),
        "status": LeaveRecord.Status.APPROVED,
        "reviewed_by": admin,
        "reviewed_at": review_time,
    }
    LeaveRecord.objects.create(**leave_fields)
    with pytest.raises(ValidationError):
        LeaveRecord.objects.create(
            **{
                **leave_fields,
                "start_date": date(2025, 2, 7),
                "end_date": date(2025, 2, 10),
            }
        )


def test_attendance_events_are_unique_and_checkout_requires_checkin():
    school = make_school()
    staff_profile = make_staff(school)
    device = make_device(school, staff_profile)
    check_out_attempt = make_attempt(
        school, staff_profile, device, AttendanceAttempt.AttemptType.CHECK_OUT, "out"
    )
    with pytest.raises(ValidationError):
        AttendanceEvent.objects.create(
            school=school,
            staff_profile=staff_profile,
            device=device,
            attendance_attempt=check_out_attempt,
            attendance_date=check_out_attempt.attendance_date,
            event_type=AttendanceEvent.EventType.CHECK_OUT,
        )

    check_in_attempt = make_attempt(
        school, staff_profile, device, AttendanceAttempt.AttemptType.CHECK_IN, "in"
    )
    AttendanceEvent.objects.create(
        school=school,
        staff_profile=staff_profile,
        device=device,
        attendance_attempt=check_in_attempt,
        attendance_date=check_in_attempt.attendance_date,
        event_type=AttendanceEvent.EventType.CHECK_IN,
    )
    check_out = AttendanceEvent.objects.create(
        school=school,
        staff_profile=staff_profile,
        device=device,
        attendance_attempt=check_out_attempt,
        attendance_date=check_out_attempt.attendance_date,
        event_type=AttendanceEvent.EventType.CHECK_OUT,
    )
    duplicate_attempt = make_attempt(
        school, staff_profile, device, AttendanceAttempt.AttemptType.CHECK_IN, "in-2"
    )
    with pytest.raises(ValidationError):
        AttendanceEvent.objects.create(
            school=school,
            staff_profile=staff_profile,
            device=device,
            attendance_attempt=duplicate_attempt,
            attendance_date=check_out.attendance_date,
            event_type=AttendanceEvent.EventType.CHECK_IN,
        )


def test_attendance_record_is_unique_per_staff_member_and_date():
    school = make_school()
    staff_profile = make_staff(school)
    fields = {
        "school": school,
        "staff_profile": staff_profile,
        "attendance_date": date(2025, 4, 1),
        "status": AttendanceRecord.Status.NOT_YET_CHECKED_IN,
        "calculated_at": timezone.now(),
    }
    AttendanceRecord.objects.create(**fields)
    with pytest.raises(ValidationError):
        AttendanceRecord.objects.create(**fields)


def test_cross_school_staff_device_and_attendance_links_are_rejected():
    school_one = make_school()
    school_two = make_school("SCH-2")
    foreign_user = make_user(school_two, "foreign")
    with pytest.raises(ValidationError):
        StaffProfile.objects.create(
            school=school_one,
            user=foreign_user,
            employee_number="EMP-X",
            first_name="Foreign",
            last_name="User",
            date_joined=date(2024, 1, 1),
        )

    local_staff = make_staff(school_one)
    foreign_device = make_device(school_two, make_staff(school_two, username="other"))
    attempt = AttendanceAttempt(
        school=school_one,
        staff_profile=local_staff,
        device=foreign_device,
        attempt_type=AttendanceAttempt.AttemptType.CHECK_IN,
        attendance_date=date(2025, 6, 2),
        client_occurred_at=timezone.now(),
        latitude=Decimal("0"),
        longitude=Decimal("0"),
        location_accuracy=Decimal("1"),
        idempotency_key="cross-school",
    )
    with pytest.raises(ValidationError):
        attempt.save()


def test_device_revocation_and_school_deactivation_preserve_history():
    school = make_school()
    device = make_device(school, make_staff(school))
    DeviceEvent.objects.create(
        school=school,
        device=device,
        event_type=DeviceEvent.EventType.ENROLLMENT,
    )
    device.status = RegisteredDevice.Status.REVOKED
    device.revoked_at = timezone.now()
    device.save()
    school.status = School.Status.INACTIVE
    school.save()

    assert RegisteredDevice.objects.get(pk=device.pk).status == "REVOKED"
    assert DeviceEvent.objects.filter(device=device).count() == 1
    with pytest.raises(ProtectedError):
        school.delete()


def test_append_only_device_events_reject_updates_and_deletes():
    school = make_school()
    event = DeviceEvent.objects.create(
        school=school,
        device=make_device(school, make_staff(school)),
        event_type=DeviceEvent.EventType.ENROLLMENT,
    )
    event.event_type = DeviceEvent.EventType.APPROVAL
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
