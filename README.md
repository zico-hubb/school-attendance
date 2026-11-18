# School Attendance Management

Initial monorepo foundation for a multi-tenant school attendance SaaS for
Kenyan schools. It contains a Django REST API, a React administration
dashboard, and one shared React/Capacitor staff application. School-code
authentication, school-scoped department and staff identity APIs, device
management, location configuration, scheduling, and leave administration are
implemented; attendance workflows and native verification are not.

## Architecture and structure

```text
backend/       Django REST Framework API and pytest suite
dashboard/     React + TypeScript + Vite administration app
mobile/        Shared React + TypeScript + Capacitor staff app
docs/          Architecture, API, database, security, and platform notes
infrastructure/azure/  Azure deployment planning only
```

See [docs/architecture.md](docs/architecture.md) for boundaries and data flow.

## Prerequisites

- Python 3.11 or later (3.11 tested for this initial setup)
- Node.js 22 or later and npm
- PostgreSQL 18 for running the normal Django development server (the local
  `school_attendance` database has been migrated using the dedicated
  `school_attendance_user` role)
- Git
- Android Studio/SDK only for native Android development; macOS/Xcode for native iOS workflows

Versions verified on the Dell: Python 3.11.9, Node.js 22.19.0, npm 10.9.3, Django 5.2.19, React 19.3.1, Vite 8.3.8, and Capacitor 8.6.0. See the package manifests and `backend/requirements.lock` for the installed dependency versions.

## Install and configure

At the repository root:

```powershell
npm install
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item dashboard\.env.example dashboard\.env
Copy-Item mobile\.env.example mobile\.env
```

Set a local `DJANGO_SECRET_KEY` and the PostgreSQL password in `backend\.env`.
The example uses `school_attendance` at `127.0.0.1:5432` with the dedicated
`school_attendance_user`; it contains placeholders, not credentials. The local
PostgreSQL 18 database is initialized and its migrations have been applied. Do
not put real secrets in Git.

The root `.env.example` is an aggregate reference. The dashboard and mobile Vite apps load their own `.env` files; adjust `VITE_API_BASE_URL` if the backend URL differs from `http://127.0.0.1:8000/api/v1`.

## Backend

From the repository root:

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.lock
Set-Location backend
python manage.py migrate
python manage.py runserver
```

Health check: `GET http://127.0.0.1:8000/api/v1/health/`.

The V1 Django models are divided across the `schools`, `accounts`, `staff`,
`devices`, `locations`, `scheduling`, `leave_management`, `attendance`, and `audit`
apps. Their initial migrations have been applied to local PostgreSQL 18. See
[docs/database-design.md](docs/database-design.md) for tenant-integrity and
validation details. Additive migrations for temporary-password state,
school-default schedules, schedule exceptions, exceptional calendar working
times, and leave workflow metadata have been generated but not applied during
this implementation. Apply pending migrations only after confirming the
target database and maintenance window.

## Dashboard and staff app

Start both Vite development servers with `npm run dev`, or start one with `npm run dev:dashboard` and `npm run dev:mobile`.

- Dashboard: <http://localhost:5173>
- Staff app in browser: <http://localhost:5174>

The dashboard reports backend availability; neither app invents school records or attendance metrics.

## Capacitor

Capacitor dependencies and shared app configuration are installed. The Android project has been generated and synchronized; no Android build has been run because Android Studio/SDK is not installed on this Dell. From `mobile/` after Android Studio/SDK is configured:

```powershell
npm run build
npm run cap -- sync android
npm run cap -- open android
```

On a Mac with Xcode, use `npm run cap -- add ios`, `npm run cap -- sync ios`, and `npm run cap -- open ios`. The iOS project has not been generated. Native builds, signing, permissions, and plugin behavior have not been verified by browser builds.

## Tests and builds

```powershell
npm test
npm run typecheck
npm run build
```

Backend tests and checks (from `backend/`, with dependencies installed):

```powershell
python -m pytest --ds=config.settings.development --reuse-db
python manage.py check
python manage.py makemigrations --check --dry-run
```

The test settings use PostgreSQL, with Django's isolated
`test_school_attendance` database. The local application role does not have
`CREATEDB`; the test database must already exist and be owned by
`school_attendance_user`. `--reuse-db` reuses it without changing the
`school_attendance` development database. Normal development and production use
PostgreSQL.

## Administration authentication

The dashboard uses `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`,
and `POST /api/v1/auth/logout/`. Access tokens remain in memory, while the
refresh credential and backend-issued identity are held in `sessionStorage`;
refresh state survives a normal page refresh but not closing the browser
session. Session storage is not an HttpOnly secure cookie and must not be
presented as equivalent cookie security.

The login page accepts a school code, username, and password. Only
`SCHOOL_ADMIN` and `ATTENDANCE_MANAGER` identities are admitted to the web
shell. `STAFF` identities are rejected and directed to the mobile application.
Navigation is role-aware, but every backend endpoint remains authoritative.

Set `VITE_API_BASE_URL` in `dashboard/.env`; it defaults to
`http://127.0.0.1:8000/api/v1` for local development. Staff directory operations
use the school-scoped `/api/v1/staff/` endpoints. Logout clears local state even
when the logout request cannot reach the backend; a failed refresh also clears
the local session.

## Limitations

-   The versioned API has health, authentication, department and staff identity,
  device lifecycle, location configuration, schedule/calendar, and leave
  endpoints. Public registration, attendance workflows/classification,
  administrator attendance corrections, and reporting are not implemented.
- Native Wi-Fi, GPS, device identity, biometrics, and platform plugins are unavailable.
- Android SDK tooling is required for Android project continuation/builds; Xcode and macOS are required for iOS project/build/signing.
- Azure deployment remains unprovisioned.

Additional plans: [database design](docs/database-design.md), [API contract](docs/api-contracts.md), [device security](docs/device-security.md), [network verification](docs/network-verification.md), [mobile support](docs/mobile-platform-support.md), [deployment](docs/deployment-guide.md).
