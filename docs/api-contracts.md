# API contracts

All API routes use Django REST Framework URL-path versioning. Version `1` is
currently supported.

## Health

- `GET /api/v1/health/`
- Success: HTTP `200`
- JSON response: `{"status":"ok","version":"1"}`
- Unsupported methods return HTTP `405`.

The health endpoint is public.

## Authentication

### Login

`POST /api/v1/auth/login/` is public and does not provide registration.
School identity is resolved on the server from `school_code`; a client-supplied
school ID is not an authentication input.

Request:

```json
{
  "school_code": "NAIROBI-001",
  "username": "jane.doe",
  "password": "<password>"
}
```

Success (`200`):

```json
{
  "access_token": "<signed-access-token>",
  "refresh_token": "<opaque-refresh-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_expires_at": "<ISO-8601 timestamp>",
  "device_status": "NOT_ENROLLED",
  "session_status": "BOOTSTRAP",
  "user": {
    "id": "<user-uuid>",
    "username": "jane.doe",
    "role": "STAFF",
    "school_code": "NAIROBI-001"
  }
}
```

The access token is a Django-signed bearer token, accepted for 15 minutes.
Refresh tokens are random opaque values; only their SHA-256 hashes and hashes
of previously used refresh values are stored in `UserSession`. Refresh-token
lifetime is 30 days. Each successful refresh rotates the token. Reuse of a
previously rotated value revokes that token family.

Password login creates a bootstrap session for staff, not an attendance-trusted
device session. Its `device_status` is `NOT_ENROLLED`, `PENDING`, `ACTIVE`,
`REVOKED`, or `REJECTED`; `session_status` is `BOOTSTRAP`. Bootstrap staff
sessions cannot refresh. A staff device must complete the signed
device-authentication flow below to establish a refreshable device-bound
session. Non-staff accounts use `device_status: NOT_APPLICABLE` and retain
account-bound sessions. Inactive accounts return `403` with
`{"state":"ACCOUNT_INACTIVE","detail":"The account is inactive."}` only after
the submitted password is verified.

`POST /api/v1/auth/refresh/` accepts
`{"refresh_token":"<opaque-refresh-token>"}` and returns a rotated token pair
in the same response shape. Staff refresh requires a session bound to the
staff member's active registered device; bootstrap staff sessions are rejected.

Access tokens are signed, not encrypted; use HTTPS and do not log bearer or
refresh token values.

`POST /api/v1/auth/logout/` requires a bearer access token and returns `204`.
It revokes the associated session, invalidating both its access and refresh
tokens.

Authentication errors for an unknown school, unknown username, or wrong
password return the same `401` response:

```json
{"detail":"Invalid school code, username, or password."}
```

Missing or malformed login fields return `400` with a generic validation
message. Invalid, expired, or revoked refresh credentials return `401` with
`{"detail":"Invalid or expired refresh token."}`. Missing or malformed refresh
fields return `400` with the same generic message.

Example:

```sh
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"school_code":"NAIROBI-001","username":"jane.doe","password":"<password>"}'
```

Send access tokens on protected requests as
`Authorization: Bearer <signed-access-token>`.

## Device registration and trusted sessions

The backend accepts P-256 ECDSA public keys in PEM-encoded
SubjectPublicKeyInfo format and verifies ECDSA/SHA-256 signatures encoded as
standard Base64 DER. The API does not receive private keys or hardware
attestation. Enrollment begins from an authenticated staff bootstrap session;
the school is taken from that account, never from request data.

### Enrollment challenge and enrollment

`POST /api/v1/devices/enrollment-challenge/` returns a random, one-time
challenge valid for five minutes. Its hash, user, school, purpose, and expiry
are stored server-side. Sign the UTF-8 bytes formed by joining these lines
with newline characters:

```text
school-attendance:device-enrollment:v1
<challenge>
<user_uuid>
<school_uuid>
```

The challenge response includes the user/staff identifiers, `school_id`,
expiry, and algorithm, so the client has the context required to construct the
message; `school_id` is informational and is never accepted as a tenancy input.

`POST /api/v1/devices/enroll/` accepts:

```json
{
  "platform": "ANDROID",
  "device_name": "Staff phone",
  "public_key": "-----BEGIN PUBLIC KEY-----\n<base64 DER SPKI>\n-----END PUBLIC KEY-----",
  "challenge": "<challenge>",
  "signature": "<base64 DER ECDSA/SHA-256 signature>"
}
```

A valid signature consumes the challenge and creates a `PENDING` device and
public-key record. Invalid, expired, reused, or another user's challenge is
rejected. The server verifies P-256 key type and signature; client-reported
verification flags are not accepted. The initial workflow always requires
school-admin approval.

Challenge response (`201`):

```json
{
  "challenge": "<random-one-time-value>",
  "expires_at": "<ISO-8601 timestamp>",
  "algorithm": "ECDSA_P256_SHA256",
  "signature_message": "school-attendance:device-enrollment:v1\n<challenge>\n<user_uuid>\n<school_uuid>",
  "staff_id": "<staff-profile-uuid>",
  "school_id": "<school-uuid>"
}
```

Enrollment response (`202`):

```json
{
  "device": {
    "id": "<device-uuid>",
    "platform": "ANDROID",
    "device_name": "Staff phone",
    "status": "PENDING",
    "keys": [
      {
        "algorithm": "ECDSA_P256_SHA256",
        "fingerprint": "<sha256-public-key-fingerprint>",
        "key_version": 1,
        "status": "ACTIVE"
      }
    ]
  },
  "state": "PENDING",
  "detail": "Device enrollment is waiting for school administrator approval."
}
```

### School-admin device management

All management routes require a `SCHOOL_ADMIN` account and scope every query
to that administrator's school. A foreign-school device UUID returns `404`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/devices/` | List devices in the administrator's school |
| `GET` | `/api/v1/devices/<device-uuid>/` | Device details, key metadata, and history |
| `POST` | `/api/v1/devices/<device-uuid>/approve/` | Activate a pending device |
| `POST` | `/api/v1/devices/<device-uuid>/reject/` | Reject a pending device; optional `reason` |
| `POST` | `/api/v1/devices/<device-uuid>/revoke/` | Revoke an active device; optional `reason` |

Approve requests use an empty JSON object. Reject/revoke requests may include
`{"reason":"Phone reported lost"}`. Successful decisions return the updated
device object with status and timestamps. The list returns an array of devices;
detail adds device events and audit history. Public-key contents are not
returned; key algorithm, fingerprint, version, status, and lifecycle timestamps
are included.

Approval and enrollment serialize on the staff profile and the database enforces
one active device per staff member. Rejection and revocation preserve device,
key, attendance, and audit history. Revocation retires the key and revokes all
sessions for that device. A replacement phone always creates its own key and
device record; the administrator revokes the old phone before approving the
replacement.

### Device-bound sessions

After approval, the mobile app uses its active key to establish a trusted
session:

1. `POST /api/v1/auth/device-challenge/` returns a challenge bound to the
   authenticated staff user, school, active device, purpose, and expiry,
   including `school_id` and `device_id` for message construction.
2. Sign these UTF-8 newline-joined bytes with the registered key:

   ```text
   school-attendance:device-authentication:v1
   <challenge>
   <user_uuid>
   <school_uuid>
   <device_uuid>
   ```
3. `POST /api/v1/auth/device-session/` accepts
   `{"challenge":"<challenge>","signature":"<base64 DER signature>"}`.
   On success it returns the standard token response with
   `session_status: DEVICE_BOUND`.

The device-authentication challenge response has the same challenge, expiry,
algorithm, and signature-message fields as enrollment, plus `school_id` and
`device_id`. A successful device-session response uses the standard login
token shape and reports the active device state.

Device-bound refresh checks the device and active key on every rotation.
Revoked devices cannot authenticate or refresh. Logout revokes the current
session. The server records only refresh-token hashes, including hashes needed
for reuse detection. No attendance endpoints are implemented by this
milestone; a future attendance API must explicitly require a device-bound
session.

The Android implementation must generate and retain the P-256 private key in
Android Keystore, prefer hardware-backed storage and StrongBox when supported,
and sign server challenges without exporting the key. The iOS implementation
must use the Security framework and Secure Enclave P-256 keys where supported;
otherwise it must use an explicitly documented Keychain-protected fallback.
Neither native implementation is included in this backend milestone.

### Device-related states and errors

- `NOT_ENROLLED`: no device record exists.
- `PENDING`: enrollment awaits administrator approval.
- `ACTIVE`: an approved device exists; a bootstrap session still needs signed
  device authentication.
- `REVOKED` / `REJECTED`: a prior device exists but is not trusted.
- `ACCOUNT_INACTIVE`: returned only after a correct password is supplied for
  an inactive account.
- `400`: invalid request or challenge/signature.
- `401`: missing, expired, revoked, or invalid bearer/refresh credentials.
- `403`: authenticated role denied, or the account is inactive.
- `404`: requested device does not exist in the administrator's school.
- `409`: active-device conflict or an invalid lifecycle transition.

## Staff identity management

Every staff-management endpoint requires the `SCHOOL_ADMIN` role. Staff and
attendance-manager roles cannot list, create, retrieve, or update staff through
these endpoints. There is no public user or staff endpoint and no delete
endpoint.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/staff/` | List staff in the authenticated administrator's school |
| `POST` | `/api/v1/staff/` | Create a staff account and profile |
| `GET` | `/api/v1/staff/<staff-uuid>/` | Retrieve a profile in that school |
| `PATCH` | `/api/v1/staff/<staff-uuid>/` | Update permitted profile/account fields |

Creation example:

```json
{
  "username": "jane.doe",
  "password": "<initial-password>",
  "email": "jane@example.test",
  "phone": "+254700000000",
  "employee_number": "EMP-1024",
  "first_name": "Jane",
  "last_name": "Doe",
  "department": "<department-uuid>",
  "job_title": "Teacher",
  "date_joined": "2025-01-02"
}
```

The server assigns the user's school from the authenticated administrator and
always creates the application role `STAFF`; `school`, `school_id`, role, and
`is_staff` are not writable fields. Passwords are checked using Django password
validators and stored using Django's password hashing. The response includes
the user and profile IDs but never returns the password.

The `201` response contains the profile ID, linked `user_id`, username, role,
active state, employee number, name, department, job title, employment status,
and employment dates. It does not expose a school ID.

`PATCH` permits `email`, `phone`, `is_active`, `employee_number`, `first_name`,
`last_name`, `department`, `job_title`, `employment_status`, `date_joined`, and
`date_left`. Setting `is_active` to `false` deactivates the account without
deleting its user, profile, or related history. Client-supplied school and
unknown fields are rejected.

All profile querysets are scoped to the authenticated administrator's school.
Requests for another school's profile return `404`, including attempts using a
foreign profile UUID. User IDs do not authorize or change the tenant scope.

## School location and network configuration

These authenticated APIs configure the school's attendance-verification
environment. They do not perform attendance verification or collect a user's
current GPS position. Send a bearer access token on every request.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/locations/zones/` | List attendance zones in the caller's school |
| `POST` | `/api/v1/locations/zones/` | Create an attendance zone |
| `GET` | `/api/v1/locations/zones/<zone-uuid>/` | Retrieve a zone |
| `PATCH` | `/api/v1/locations/zones/<zone-uuid>/` | Update a zone or change its active status |
| `GET` | `/api/v1/locations/access-points/` | List approved access points in the caller's school |
| `POST` | `/api/v1/locations/access-points/` | Register an access point |
| `GET` | `/api/v1/locations/access-points/<access-point-uuid>/` | Retrieve an access point |
| `PATCH` | `/api/v1/locations/access-points/<access-point-uuid>/` | Update an access point or change its active status |

Successful list, retrieve, and patch requests return `200`; creates return
`201`.

`SCHOOL_ADMIN` can read and mutate configuration. `ATTENDANCE_MANAGER` can
read it but receives `403` for mutations. `STAFF` cannot access these routes.
All requests require authentication; unauthenticated requests receive `401`.

Zone creation accepts:

```json
{
  "name": "Main Campus",
  "latitude": "-1.292066",
  "longitude": "36.821946",
  "radius_meters": 500
}
```

`PATCH` accepts any subset of `name`, `latitude`, `longitude`,
`radius_meters`, and `is_active`. Latitude must be between -90 and 90,
longitude between -180 and 180, and radius must be positive and no greater
than the configurable `MAX_ATTENDANCE_ZONE_RADIUS_METERS` (default 5000m,
database ceiling 10000m). Zone names are unique within a school. Responses
include `id`, the supplied configuration fields, `is_active`, `created_at`,
and `updated_at`; list responses are arrays.

Access-point registration accepts:

```json
{
  "attendance_zone": "<zone-uuid>",
  "bssid": "aa-bb-cc-dd-ee-10",
  "name": "Library AP",
  "location_notes": "North entrance"
}
```

The referenced zone must belong to the caller's school. BSSIDs may be supplied
as compact 12-hex-digit, colon-separated, hyphen-separated, or dotted
six-byte MAC-style values. They are stored and returned uppercase in
colon-separated form (for example, `AA:BB:CC:DD:EE:10`). Invalid, multicast,
and all-zero addresses are rejected. BSSIDs must be unique within a school;
the same BSSID may be registered in another school. An access point's BSSID
and zone are immutable after registration. `PATCH` accepts any subset of
`name`, `location_notes`, and `is_active`. Responses include `id`,
`attendance_zone`, canonical `bssid`, `name`, `location_notes`, `is_active`,
`created_at`, and `updated_at`.

Client-provided school/owner fields and unsupported fields are rejected.
Every query is scoped to the authenticated user's school; a foreign-school
zone or access-point UUID returns the same `404` as an unknown UUID. A foreign
zone supplied during access-point registration is rejected as invalid input.
Use deactivation rather than deletion to preserve configuration and audit
history. Successful creates, updates, and status changes are recorded in the
existing audit log with actor, school, action, object, and before/after
metadata; a failed mutation does not create a success audit record.

Zone coordinates and BSSIDs are configuration data, not proof of presence.
GPS can be inaccurate or manipulated, and a BSSID can be spoofed; a future
attendance engine must treat them as corroborating signals rather than secure
identity or standalone evidence. These endpoints do not yet verify location
or attendance.

## Common errors and roles

- `400`: invalid or incomplete request data.
- `401`: missing, invalid, expired, or revoked authentication credentials.
- `403`: authenticated user lacks the role required for the requested operation.
- `404`: requested staff profile or location/network configuration is not
  present in the caller's school.
- `405`: unsupported method, including staff deletion.

The account roles are `SCHOOL_ADMIN`, `ATTENDANCE_MANAGER`, and `STAFF`.
This milestone only grants staff identity-management operations to
`SCHOOL_ADMIN`. It does not implement attendance APIs or grant an administrator
attendance privileges for another employee. An administrator with a staff
profile receives no attendance-verification bypass; attendance verification is
not part of this milestone.
