# Database design

PostgreSQL is the configured development and production database. The local
development environment has been verified on PostgreSQL 18 using the
`school_attendance` database and the dedicated `school_attendance_user` role at
`127.0.0.1:5432`. Connection values are loaded from the ignored `backend/.env`;
the example file contains placeholders only. The initial V1 migrations were
applied normally to the newly created, empty development database. Additive
migrations for temporary-password state, school-default assignments,
date-exception/calendar times, and leave transition metadata have since been
generated but were not applied to that database during implementation.

## App boundaries

- `schools`: schools and departments.
- `accounts`: the school-scoped custom user and school-code authentication backend.
- `staff`: staff profiles.
- `devices`: registered devices, public keys, device events, sessions, and challenges.
- `locations`: attendance zones and approved Wi-Fi access points.
- `scheduling`: schedules, versions, weekday definitions, assignments, and exceptions.
- `leave_management`: school calendar events, leave types, and administrator-managed leave.
- `attendance`: immutable submitted attempts and accepted events, plus daily records and
  recalculation history.
- `audit`: append-only audit logs.

Every tenant-owned model has an explicit school foreign key. Related-object
tenant-consistency validation runs when models are saved; school ownership cannot be
changed after record creation. Historical relationships use `PROTECT`, while
deactivation and revocation are represented by status fields and timestamps.

Database constraints enforce scoped uniqueness, idempotency, accepted-event
uniqueness, valid weekday ranges, and other local invariants. Cross-row date-range
overlap rules for schedule versions, schedule assignments, and approved leave are
validated transactionally in application code with target-row locking; calendar
events also reject overlapping ranges within a school or department scope. These
are not PostgreSQL exclusion constraints.

The custom `accounts.User` model is configured before the initial migrations.
Usernames are normalized and unique within a school, and the custom backend requires
`school_code`, `username`, and `password`. Login APIs and public registration are not
part of this foundation.

The pytest settings inherit PostgreSQL configuration; they do not switch to
SQLite. The local application role does not have `CREATEDB`, so PostgreSQL-backed
pytest runs must not be pointed at the development database or granted
database-creation privileges. A PostgreSQL administrator created a separate
`test_school_attendance` database owned by `school_attendance_user`. Run
`python -m pytest --ds=config.settings.development --reuse-db` from `backend/` to
reuse it without expanding the app role's privileges. The configuration test
asserts the active test connection uses this database, separately from
`school_attendance`. PostgreSQL 18 migration state, key unique/partial indexes,
and foreign-key delete rules have been inspected.
