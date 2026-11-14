# Device security

The mobile app defines TypeScript contracts for public-key registration and
challenge signing. Its current adapter explicitly reports device identity as
unavailable; it does not generate keys, perform cryptography, authenticate
devices, or claim successful verification.

The backend protocol accepts P-256 public keys in PEM SubjectPublicKeyInfo
format and ECDSA/SHA-256 signatures in Base64-encoded DER form. It verifies
possession of a key against a short-lived, single-use challenge bound to a
staff user and school. Device enrollment remains pending until approved by a
same-school administrator. A second signed challenge is required before
issuing a device-bound refresh session. Public-key possession is not proof of
hardware backing or platform attestation.

### Native implementation boundary

Android must generate the P-256 pair with Android Keystore, retain a
non-exportable private key, prefer hardware-backed storage, request StrongBox
when supported, and sign the exact backend challenge bytes. The implementation
must persist the key alias and reuse the same key across app launches.

iOS must use Apple's Security framework with a P-256 Secure Enclave key when
available. If Secure Enclave key creation is unavailable, the fallback must be
explicitly documented and use an appropriate Keychain protection class without
claiming Secure Enclave guarantees. Native key persistence and signing must
never export the private key. iOS and Android hardware-security guarantees
must not be treated as identical.

No native Android or iOS key-generation implementation is included. Browser
JavaScript cryptography is not an acceptable replacement for the native
platform operations. iOS Secure Enclave keys require a Mac/Xcode build and
physical-device verification before any implementation can be claimed complete.
