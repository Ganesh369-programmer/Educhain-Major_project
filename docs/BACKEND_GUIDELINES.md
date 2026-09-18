# Backend Guidelines (Django + DRF)

## Suggested Architecture

```
backend/
├── config/              # settings, urls, wsgi/asgi
├── apps/
│   ├── accounts/         # User model, auth, roles
│   ├── institutions/      # Institution, IssuerProfile, KYC review
│   ├── credentials/       # Credential, CredentialShare, issuance/revocation
│   ├── verification/      # public verification endpoints, VerificationRecord
│   ├── recruiters/        # RecruiterProfile, recruiter-facing views
│   └── blockchain/        # web3.py wrapper — the ONLY app that talks to the chain
└── manage.py
```

Deviation from this structure is fine if a clearly better organization emerges — document the reason in a commit message and update this file.

## App Responsibilities

- **accounts**: `User` model, registration/login/refresh views, role definitions, base permission classes.
- **institutions**: institution registration, KYC document handling, admin approval/rejection, calls into `blockchain` app to whitelist on approval.
- **credentials**: issuance (single + batch), revocation, listing — calls into `blockchain` app for on-chain writes/reads, calls IPFS client for document storage.
- **verification**: public verification endpoints, `VerificationRecord` logging, hash comparison logic.
- **recruiters**: recruiter profile and recruiter-facing read views (mostly thin wrappers calling `verification`/`credentials`).
- **blockchain**: `Web3` client setup, contract ABI/address loading, typed wrapper functions (`approve_issuer()`, `issue_credential()`, `revoke_credential()`, `verify_credential()`) that every other app calls instead of touching `web3.py` directly.

## Models

- One `models.py` per app, matching `DATABASE_SCHEMA.md` exactly. If a field is added/removed, update `DATABASE_SCHEMA.md` in the same change.
- Use Django's built-in `UUIDField` for primary keys where the schema specifies UUID/PK.
- Use `choices=` enums for all status/role fields rather than free-text strings.

## Serializers

- One serializer per model per use-case (e.g., `InstitutionRegisterSerializer` vs. `InstitutionDetailSerializer`) rather than one giant serializer with conditional fields.
- All input validation (format checks, required fields, cross-field checks like wallet-address checksum) happens in serializers, not in views.

## Views / ViewSets

- Prefer DRF `ViewSet`/`GenericAPIView` classes over raw function views for consistency.
- Keep views thin: validate → call a service function → serialize response. Business logic (e.g., "what happens on institution approval") belongs in a `services.py` per app, not inline in the view.

## Permissions

- Custom permission classes per role/ownership check (`IsAdmin`, `IsApprovedIssuer`, `IsCredentialOwnerOrIssuer`, etc.) in a shared `apps/accounts/permissions.py`.
- Every view explicitly declares `permission_classes` — never rely on a default that happens to be permissive.

## Services / Utilities

- `services.py` per app for multi-step business logic (e.g., `institutions/services.py::approve_institution()` which updates the DB row AND calls `blockchain.approve_issuer()` inside a transaction-safe flow).
- `utils/` for pure helper functions (hashing, GST/CIN format validation, CSV parsing for batch issuance).

## Database Transactions

- Any operation that writes to both the database and the blockchain should: (1) write the off-chain record in a pending state, (2) submit the on-chain transaction, (3) update the off-chain record to confirmed/failed based on the receipt — wrapped so a failure at step 2 doesn't leave a false "confirmed" DB row. Use Django's `transaction.atomic()` for the DB portion; treat the blockchain call as an external side effect outside the DB transaction boundary (it cannot be rolled back once submitted).

## Error Handling & Logging

- Centralized DRF exception handler mapping internal exceptions to the standard `{ "detail", "code" }` shape from `API_SPECIFICATION.md`.
- Log (not print) all blockchain call failures with the transaction hash (if any) and the triggering user/institution ID, without logging any secret/private key material.

## Testing

- `pytest` + `pytest-django` + DRF's `APIClient`.
- Minimum coverage: permission checks (each role gets 403 where expected), the institution approval → whitelist flow, the issue → verify → revoke flow (mocking the blockchain layer for speed, plus a smaller set of tests against a local Hardhat node for true integration).

## Environment Configuration

- All settings that vary per environment come from `.env` via `django-environ` or similar — never hardcoded in `settings.py`.
- `settings.py` should fail fast (raise on startup) if a required env var is missing, rather than silently defaulting to an insecure value.
