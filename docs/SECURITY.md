# Security

## Password Security

- Django's default password hasher (PBKDF2 or Argon2). Never store, log, or return plaintext passwords.
- Enforce minimum length/complexity via `AUTH_PASSWORD_VALIDATORS`.

## JWT Security

- Short-lived access tokens, rotated refresh tokens with blacklist-on-use (see `AUTHENTICATION.md`).
- Signing key (`JWT_SIGNING_KEY`) only in environment variables, distinct from `DJANGO_SECRET_KEY` where practical.
- Tokens never logged.

## CORS

- `CORS_ALLOWED_ORIGINS` restricted to the known frontend origin(s) — never `CORS_ALLOW_ALL_ORIGINS = True` outside local development.

## CSRF

- API is token-authenticated (JWT via header), so CSRF protection is primarily relevant only if any session/cookie-based auth is ever added (e.g., an httpOnly refresh cookie) — in that case, enable Django's CSRF middleware for those specific endpoints.

## Input Validation

- Every write endpoint validates input via DRF serializers server-side — client-side validation is UX only.
- File uploads (KYC documents, certificate documents) validated for type and size before storage.

## SQL Injection Prevention

- Use Django ORM exclusively for queries; no raw SQL string interpolation. If raw SQL is ever unavoidable, use parameterized queries only.

## XSS Protection

- React escapes rendered content by default — avoid `dangerouslySetInnerHTML` entirely unless content is sanitized.
- API responses are JSON, not rendered HTML, reducing reflected-XSS surface.

## Rate Limiting

- Apply DRF throttling to: `/auth/login/`, `/auth/register/`, `/verify/{credential_id}/`, `/verify/upload/` — these are the most abuse-prone (credential stuffing, verification enumeration).

## API Authorization

- Every protected endpoint checks role AND, where relevant, object ownership (a student can only share their own credential; an issuer can only issue/revoke for their own approved institution) — see `USER_ROLES_AND_PERMISSIONS.md`.
- **Never rely only on frontend role restrictions.** The frontend hiding a button is a UX nicety, not a security control — the backend re-checks every time.

## Sensitive Data Protection — On-Chain vs Off-Chain

This is the central security design decision of the project:

| Data | Where it lives | Why |
|---|---|---|
| Credential ID, document hash, issuer address, timestamp, revoked flag | On-chain | Needed for tamper-evident, third-party verifiable proof; none of it is personally identifying on its own |
| Full certificate document | IPFS (content-addressed, off-chain) | Too large/costly for on-chain storage; hash on-chain still detects tampering |
| Student PII (name, email, phone, DOB, full marksheet) | Django DB only | Blockchain records are public and permanent — PII must never be irrevocably public. Access is controlled by the API's auth/permission layer instead |
| Institution KYC documents | Django DB / off-chain file storage only | Same reasoning — sensitive business documents, access-controlled, not permanently public |

Rule of thumb used throughout the docs: **if it's needed to independently prove "this exact document hasn't changed" or "this address is an authorized issuer," it can go on-chain. If it's needed to know *who* a person is, it stays off-chain.**

## Environment Variables & Secret Management

- All secrets (DB credentials, JWT signing key, blockchain RPC URL, platform private key, IPFS credentials) live in `.env`, loaded via `django-environ`/`python-dotenv`.
- `.env` is git-ignored; only `.env.example` (with empty/placeholder values) is committed.
- Never hardcode: passwords, JWT secrets, API keys, private keys, database passwords — anywhere in source, comments, or documentation examples with real values.

## Blockchain Private Key Protection

- `PLATFORM_ADMIN_PRIVATE_KEY` (used only for admin-triggered on-chain calls like `approveIssuer` and `revokeIssuer`) lives in the backend environment only — never sent to the frontend, never logged, never committed.
- For institution credential signing, private keys are never accepted over HTTP (neither via request bodies nor headers). The platform employs Model A (custodial wallets encrypted at rest).
- Consider a KMS/secrets manager for production; for the academic prototype, a properly git-ignored `.env` on a single trusted server is the accepted minimum.
- See `ARCHITECTURE.md`'s "MetaMask / Wallet Integration Scope" section for exactly which actions MetaMask is (and is not) used for, and the known limitation around unproven wallet-address ownership at institution registration.

## Custodial Wallet Model (Institution Signing Keys)

- **Architecture (Model A):** The platform generates and custodies each institution's signing wallet upon admin approval.
- **Encryption at Rest:** Stored in `Institution.encrypted_private_key` using Fernet symmetric encryption keyed by `WALLET_ENCRYPTION_KEY` (kept separate from `DJANGO_SECRET_KEY`). Plaintext private keys are never written to the database.
- **In-Memory Lifetime:** Keys are decrypted strictly in-memory at the moment of building and signing on-chain transactions (`issueCredential`, `batchIssueCredentials`, `revokeCredential`). The decrypted key is never logged, never returned via API responses/serializers, and never accepted from incoming requests.
- **Address Preservation:** The institution's originally submitted wallet address (e.g. from MetaMask at initial registration) is preserved in `Institution.registered_wallet_address` for audit and provenance records. The generated custodial wallet address is assigned to `Institution.wallet_address`, which is the address approved and whitelisted on-chain.
- **Security Tradeoffs & Production Alternatives:**
  - *Tradeoff:* The institution must trust the platform host not to abuse or expose the custodied private key.
  - *Production Alternative:* Non-custodial signing via the institution's own MetaMask wallet combined with an ERC-2771 / EIP-712 meta-transaction relayer or smart contract forwarder, allowing institutions to retain sole key possession while the platform covers gas or coordinates batches.

## Smart Contract Access Control

- `onlyAdmin` and `onlyApprovedIssuer` modifiers enforce whitelist rules **at the contract level**, independent of the backend — this is the second, tamper-proof layer of defense described in the fraud-prevention discussion (backend check + contract-level check).
- Contract `admin` address itself should be a dedicated, carefully-protected wallet — compromise of this key would allow arbitrary issuer whitelisting, so treat it as the highest-value secret in the system.

## Replay / Duplicate Credential Considerations

- `document_hash` is unique in the database and the contract rejects issuing a `credentialId` that already exists (`require(credentials[credentialId].issuedOn == 0, ...)`), preventing accidental or malicious duplicate issuance of the identical record.

## Credential Hash Integrity

- Hash computed server-side at issuance time from the exact stored document; verification recomputes the hash the same way and compares against the on-chain value — any difference (even one byte) fails verification.

## Audit Logging

- `VerificationRecord` logs every verification attempt (result, timestamp, optional verifier).
- `BlockchainTransaction` logs every on-chain write attempt with status and gas usage.
- Neither log stores secret material; both are readable by Admin for investigating disputes.
