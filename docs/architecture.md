# Architecture

The monorepo contains three independently developed applications:

- `backend/`: Django REST Framework API, with versioned routes under `/api/v1/` and PostgreSQL as the configured development and production database.
- `dashboard/`: browser-based React administration interface built with Vite.
- `mobile/`: one React application for staff that runs in the browser during development and is packaged for Android/iOS with Capacitor.

The dashboard and mobile app call the same API. Their `VITE_API_BASE_URL` setting points at the versioned API root; neither client implements tenant authorization or attendance rules. The backend is responsible for those decisions and future tenant isolation.

Development, test, and production settings use PostgreSQL. Pytest uses Django's
separate `test_school_attendance` database; because the application role does
not have `CREATEDB`, provision that database owned by `school_attendance_user`
and use pytest-django's `--reuse-db` option.

## Current scope

The API exposes a public health check, school-code authentication with signed
access and rotating refresh tokens, school-admin staff identity management,
and school-scoped attendance-zone and approved-Wi-Fi access-point
configuration. Public registration, attendance verification and
classification, native integrations, and dashboard/mobile workflows are not
implemented. No Azure resources or deployment configuration are provisioned.

## School location and network configuration

The `locations` app's existing attendance-zone and approved-access-point
models back `/api/v1/locations/zones/` and
`/api/v1/locations/access-points/`. Configuration ownership is always derived
from the authenticated user's school. Collection and detail querysets are
tenant-scoped, and foreign-school object IDs produce not-found responses.
Access-point records retain a required relationship to a zone in the same
school. School administrators have read/write access, attendance managers
have read-only access, and staff have no access.

Zones store campus/building coordinates and a positive radius; application
validation enforces the configurable radius maximum, while database checks
enforce coordinate bounds and a fixed upper ceiling. Approved access points
store normalized uppercase colon-separated BSSIDs with school-scoped
uniqueness. Both resource types are deactivated rather than deleted, and each
successful mutation writes actor, school, action, object, and before/after
metadata to the existing append-only audit log in the same transaction.

These APIs configure the school's verification environment only. They do not
collect GPS positions or verify attendance. GPS may be inaccurate or
manipulated, and BSSIDs can be spoofed; neither is secure proof of physical
presence or device identity. A future attendance engine must treat them only
as corroborating signals.

## Device enrollment and sessions

Device enrollment uses five-minute, single-use server challenges bound to the
authenticated staff user and school. The client generates a P-256 keypair and
signs a domain-separated UTF-8 challenge message. The backend accepts only
PEM SubjectPublicKeyInfo P-256 public keys and verifies ECDSA/SHA-256 signatures
encoded as Base64 DER. It stores the public key and SHA-256 fingerprint, never
the private key. This protocol verifies key possession, not platform
attestation or hardware provenance.

New device records start `PENDING`. A same-school administrator may approve
them to `ACTIVE` or reject them. Active devices may be revoked; revocation
retires the key and invalidates every associated session. Old records and
append-only audit events remain. Staff-profile row locks and the database's
partial unique constraint enforce one active device per staff member.

Device transitions are `PENDING -> ACTIVE -> REVOKED` or
`PENDING -> REJECTED`; terminal device records are retained. The public key
starts active with pending enrollment and is retired when its device is
rejected or revoked. Staff sessions progress from bootstrap to device-bound
only after a signed device challenge. Refresh rotates the credential hash;
logout, account deactivation, device revocation, expiry, or detected token
reuse invalidates the session.

Password login for staff establishes only a bootstrap session. A pending or
unknown device cannot establish attendance eligibility. After administrator
approval, the device proves possession with a second one-time challenge before
the backend issues a device-bound refresh session. Refresh rotates opaque
tokens, stores only hashes in per-token records (including consumed hashes), and
revokes the token family on reuse. Logout, account deactivation, and device
revocation invalidate their associated sessions. Non-staff accounts retain
account-bound sessions.

Android native work must generate a non-exportable P-256 key in Android
Keystore, prefer hardware backing and StrongBox where available, and use that
key to sign challenges. iOS native work must generate a P-256 key using
Security.framework and Secure Enclave when available; on unsupported hardware,
the app must use a documented Keychain-protected fallback and clearly
distinguish its security guarantee. Android and iOS key-storage guarantees are
not interchangeable. Native key generation, signing, hardware attestation,
Mac/Xcode builds, and physical-device tests are not included in this milestone.
