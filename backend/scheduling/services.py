from django.db.models import Case, IntegerField, Q, Value, When

from .models import (
    ScheduleAssignment,
    ScheduleException,
    ScheduleVersion,
)
from leave_management.models import SchoolCalendarEvent


def schedule_for_date(staff_profile, target_date):
    exception = (
        ScheduleException.objects.filter(
            school_id=staff_profile.school_id,
            staff_profile=staff_profile,
            exception_date=target_date,
        )
        .select_related("created_by")
        .first()
    )
    if exception is not None:
        base = _assigned_schedule_for_date(staff_profile, target_date)
        effective = {
            "is_working_day": exception.is_working_day,
            "start_time": exception.start_time,
            "end_time": exception.end_time,
            "late_after": exception.late_after,
            "absence_finalization_time": exception.absence_finalization_time,
        }
        if exception.is_working_day and base is not None:
            for field in (
                "start_time",
                "end_time",
                "late_after",
                "absence_finalization_time",
            ):
                if effective[field] is None:
                    effective[field] = getattr(base["day"], field)
        return {
            "source": "EXCEPTION",
            "exception": exception,
            "base": base,
            **effective,
        }

    calendar_event = (
        SchoolCalendarEvent.objects.filter(
            school_id=staff_profile.school_id,
            start_date__lte=target_date,
            end_date__gte=target_date,
        )
        .filter(
            Q(department__isnull=True)
            | Q(department_id=staff_profile.department_id)
        )
        .order_by(
            Case(
                When(department_id=staff_profile.department_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .first()
    )
    if calendar_event is not None:
        base = _assigned_schedule_for_date(staff_profile, target_date)
        is_working_day = (
            calendar_event.event_type
            == SchoolCalendarEvent.EventType.EXCEPTIONAL_WORKING_DAY
        )
        return {
            "source": "CALENDAR",
            "calendar_event": calendar_event,
            "base": base,
            "is_working_day": is_working_day,
            "start_time": calendar_event.start_time if is_working_day else None,
            "end_time": calendar_event.end_time if is_working_day else None,
            "late_after": calendar_event.late_after if is_working_day else None,
            "absence_finalization_time": (
                calendar_event.absence_finalization_time if is_working_day else None
            ),
        }

    return _assigned_schedule_for_date(staff_profile, target_date)


def _assigned_schedule_for_date(staff_profile, target_date):
    assignment_scopes = [
        ("STAFF", {"staff_profile": staff_profile}),
    ]
    if staff_profile.department_id:
        assignment_scopes.append(
            ("DEPARTMENT", {"department_id": staff_profile.department_id})
        )
    assignment_scopes.append(("SCHOOL", {"is_school_default": True}))

    for source, scope in assignment_scopes:
        assignment = (
            ScheduleAssignment.objects.filter(
                school_id=staff_profile.school_id,
                work_schedule__is_active=True,
                effective_from__lte=target_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=target_date))
            .filter(**scope)
            .select_related("work_schedule")
            .order_by("-effective_from")
            .first()
        )
        if assignment is None:
            continue
        version = (
            ScheduleVersion.objects.filter(
                work_schedule=assignment.work_schedule,
                is_active=True,
                effective_from__lte=target_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=target_date))
            .prefetch_related("days")
            .first()
        )
        if version is None:
            return None
        day = next(
            (item for item in version.days.all() if item.weekday == target_date.weekday()),
            None,
        )
        if day is None:
            return None
        return {
            "source": source,
            "assignment": assignment,
            "version": version,
            "day": day,
            "is_working_day": day.is_working_day,
            "start_time": day.start_time,
            "end_time": day.end_time,
            "late_after": day.late_after,
            "absence_finalization_time": day.absence_finalization_time,
        }
    return None
