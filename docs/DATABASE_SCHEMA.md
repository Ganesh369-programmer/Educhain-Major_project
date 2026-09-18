# Database Schema (Off-Chain — SQLite)

General rules:
- Every model has `id` (PK, auto), `created_at`, `updated_at` unless stated otherwise.
- On-chain data (credential hash, issuer wallet, revocation flag) is mirrored here for fast querying, but the blockchain is the source of truth for those specific fields — see the "On-chain mirror" note per model.

## User

Purpose: base authentication record for every role.

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| email | string, unique | yes | login identifier |
| password_hash | string | yes | Django's hasher |
| role | enum(ADMIN, STUDENT, ISSUER, RECRUITER) | yes | |
| is_active | bool | yes | default true |
| phone_number | string | no | |
| created_at / updated_at | datetime | yes | |

Relationships: one-to-one with `StudentProfile`, `IssuerProfile`, or `RecruiterProfile` depending on `role`.

## Institution

Purpose: the organization applying to become a credential issuer.

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| name | string | yes | |
| institution_type | enum(UNIVERSITY, PRIVATE_TRAINING_INSTITUTE, COMPANY, NGO) | yes | |
| official_website | URL | no | |
| official_email_domain | string | yes | used for domain-match validation |
| registration_number | string | yes | AICTE code / CIN / Udyam etc. |
| gst_number | string | no | validated by format/checksum |
| proof_document | file reference | yes | stored off-chain (local/S3-style storage) |
| wallet_address | string(42) | yes, unique | Ethereum address, validated checksum |
| status | enum(PENDING, APPROVED, REJECTED) | yes | default PENDING |
| trust_tier | int | no | set on approval (1=university, 2=company/NGO, 3=self-declared) |
| reviewed_by | FK → User (admin) | no | |
| reviewed_at | datetime | no | |
| rejection_reason | text | no | required if status=REJECTED |

Indexes: `wallet_address` (unique), `status`.

## IssuerProfile

Purpose: links an approved `Institution` to the `User` account(s) allowed to act as that issuer.

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| user | FK → User (role=ISSUER) | yes | |
| institution | FK → Institution | yes | |
| is_primary_contact | bool | yes | default true for the registering user |

Relationship: an Institution can have multiple IssuerProfile users (e.g., exam cell staff), but only the whitelisted `wallet_address` on Institution can trigger on-chain issuance.

## StudentProfile

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| user | FK → User (role=STUDENT), one-to-one | yes | |
| full_name | string | yes | |
| roll_number | string | no | |
| date_of_birth | date | no | |
| wallet_address | string(42) | no | optional, for wallet-based credential ownership |
| public_profile_enabled | bool | yes | default false |

## RecruiterProfile

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| user | FK → User (role=RECRUITER), one-to-one | yes | |
| company_name | string | yes | |
| company_domain | string | no | for basic recruiter-side verification |

## Credential

Purpose: off-chain metadata mirror of an on-chain credential record.

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | also used as the on-chain `credentialId` (bytes32 derived) |
| student | FK → StudentProfile | yes | |
| institution | FK → Institution | yes | issuer at time of issuance |
| credential_type | string | yes | e.g. "Degree", "Internship Certificate" |
| title | string | yes | e.g. "B.E. Computer Engineering" |
| issue_date | date | yes | |
| document_hash | string(66) | yes | SHA-256, on-chain mirror (source of truth: chain) |
| ipfs_cid | string | yes | pointer to the stored document |
| status | enum(PENDING, ACTIVE, REVOKED, INVALID) | yes | on-chain mirror for `REVOKED` |
| tx_hash | string(66) | yes | issuance transaction hash |
| revoked_at | datetime | no | |
| revocation_reason | text | no | |

Indexes: `student`, `institution`, `status`, `document_hash` (unique).

## CredentialShare

Purpose: a student-generated shareable/verification artifact.

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| credential | FK → Credential | yes | |
| share_token | string, unique | yes | used in the public URL / QR payload |
| visible_fields | JSON list | yes | which fields are exposed (selective disclosure at the app layer) |
| expires_at | datetime | no | optional expiry |
| created_at | datetime | yes | |

## VerificationRecord

Purpose: audit log of verification attempts (useful for institutions and for your project's "auditability" NFR).

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| credential | FK → Credential | yes | |
| verifier | FK → User, nullable | no | null for anonymous/public verification |
| result | enum(VALID, REVOKED, INVALID, NOT_FOUND) | yes | |
| verified_at | datetime | yes | |
| ip_address | string | no | optional, for abuse monitoring |

## BlockchainTransaction

Purpose: generic log of every on-chain write the backend performs, for debugging/audit.

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| tx_hash | string(66), unique | yes | |
| action | enum(APPROVE_ISSUER, REVOKE_ISSUER, ISSUE_CREDENTIAL, REVOKE_CREDENTIAL) | yes | |
| related_object_id | UUID | no | Institution.id or Credential.id |
| status | enum(PENDING, CONFIRMED, FAILED) | yes | |
| gas_used | int | no | |
| created_at | datetime | yes | |

## Notification

| Field | Type | Required | Notes |
|---|---|---|---|
| id | UUID/PK | yes | |
| user | FK → User | yes | |
| message | text | yes | |
| is_read | bool | yes | default false |
| created_at | datetime | yes | |

## Relationships Summary

```
User (1) ──── (1) StudentProfile / IssuerProfile / RecruiterProfile
Institution (1) ──── (many) IssuerProfile
Institution (1) ──── (many) Credential
StudentProfile (1) ──── (many) Credential
Credential (1) ──── (many) CredentialShare
Credential (1) ──── (many) VerificationRecord
Institution / Credential ──── (many) BlockchainTransaction (via related_object_id)
```

## Validation Rules (high level)

- `Institution.wallet_address` and `StudentProfile.wallet_address` must be valid checksummed Ethereum addresses.
- `Institution.status` can only move PENDING → APPROVED or PENDING → REJECTED (no reverse transitions except an explicit admin revoke, which is a separate action, not a status edit).
- `Credential.status` can only move PENDING → ACTIVE → REVOKED (no direct PENDING → REVOKED, no un-revoking).
- `Credential.document_hash` must be unique — prevents duplicate/replay issuance of an identical document.
