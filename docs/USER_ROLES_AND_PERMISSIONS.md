# User Roles and Permissions

## Roles

- **ADMIN** — platform operator. Reviews institutions, manages the on-chain whitelist, can revoke any issuer or (in exceptional cases) any credential.
- **ISSUER** — a user account tied to an `Institution`. Can issue/revoke credentials for their own institution only, and only once that institution is `APPROVED`.
- **STUDENT** — owns and shares their own credentials, manages a career profile.
- **RECRUITER** — verifies credentials, views public career profiles.

## Permission Matrix

| Feature | Admin | Student | Issuer (unapproved institution) | Issuer (approved institution) | Recruiter |
|---|---|---|---|---|---|
| Register / Login | Yes | Yes | Yes | Yes | Yes |
| Submit institution registration + KYC | Yes (on behalf, rare) | No | Yes | N/A (already done) | No |
| View own institution status | Yes | No | Yes | Yes | No |
| Approve / reject institution | Yes | No | No | No | No |
| Manage on-chain issuer whitelist | Yes | No | No | No | No |
| Issue single credential | No | No | No | Yes | No |
| Issue batch credentials | No | No | No | Yes | No |
| Revoke a credential they issued | Yes (override) | No | No | Yes | No |
| View credentials they issued | Yes | No | No | Yes | No |
| View own credentials | No | Yes | N/A | N/A | No |
| Generate share link / QR for own credential | No | Yes | No | No | No |
| Verify a credential (public) | Yes | Yes | Yes | Yes | Yes |
| View a student's public career profile | Yes | Owner only (full) | No | No | Yes (if public) |
| View verification audit history for a credential | Yes | Owner student | No | Issuing institution only | No |
| Manage own user profile | Yes | Yes | Yes | Yes | Yes |
| View platform-wide analytics | Yes | No | No | No | No |

## Notes on Enforcement

- All rows above are enforced with DRF permission classes on the backend. The frontend hides UI for actions a role cannot perform, but this is a UX convenience only — see `SECURITY.md`.
- "Issuer (unapproved institution)" has a `User` account and can log in and view their pending status, but every credential-issuance endpoint checks `Institution.status == APPROVED` server-side before proceeding, and the smart contract independently checks the whitelist mapping.
- Admin's ability to revoke a credential issued by someone else is an override for handling disputes/fraud (e.g., a whitelisted issuer later found to be compromised) — this should be logged with a mandatory reason and is distinct from routine issuer-initiated revocation.
- Recruiters only ever see credential fields the student has explicitly chosen to expose via `CredentialShare.visible_fields`, or the always-public verification status (`VALID`/`REVOKED`/`INVALID`/`NOT_FOUND`) plus non-sensitive fields like credential type and institution name.
