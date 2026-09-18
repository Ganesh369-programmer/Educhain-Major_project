# API Specification

Base URL (dev): `http://localhost:8000/api/v1/`

All authenticated requests send `Authorization: Bearer <access_token>`.
All error responses follow: `{ "detail": "human readable message", "code": "MACHINE_CODE" }`.

---

## Authentication

### POST /auth/register/
- Auth: none
- Body: `{ "email", "password", "role": "STUDENT" | "ISSUER" | "RECRUITER" }` (ADMIN accounts are not self-registrable)
- Response 201: `{ "id", "email", "role" }`
- Errors: 400 (validation, duplicate email)

### POST /auth/login/
- Auth: none
- Body: `{ "email", "password" }`
- Response 200: `{ "access", "refresh", "role" }`
- Errors: 401 (invalid credentials)

### POST /auth/refresh/
- Auth: none (refresh token in body)
- Body: `{ "refresh" }`
- Response 200: `{ "access" }`
- Errors: 401 (expired/invalid refresh token)

### POST /auth/logout/
- Auth: Bearer
- Body: `{ "refresh" }` (blacklisted)
- Response 205

---

## Users

### GET /users/me/
- Auth: Bearer (any role)
- Response 200: `{ "id", "email", "role", "profile": {...role-specific...} }`

### PATCH /users/me/
- Auth: Bearer
- Body: role-appropriate profile fields
- Response 200: updated user/profile

---

## Institutions

### POST /institutions/register/
- Auth: Bearer (role=ISSUER, the registering user)
- Body: `{ "name", "institution_type", "official_website", "official_email_domain", "registration_number", "gst_number", "wallet_address"}` (multipart/form-data)
- Response 201: `{ "id", "status": "PENDING" }`
- Errors: 400 (validation), 409 (duplicate wallet/registration number)

### GET /institutions/{id}/
- Auth: Bearer (Admin, or the institution's own ISSUER users)
- Response 200: full institution record incl. status, trust_tier

### GET /institutions/ (list, filterable by status)
- Auth: Bearer (Admin only for unrestricted list; ISSUER sees only their own)
- Query params: `status`, `institution_type`
- Response 200: paginated list

### POST /institutions/{id}/approve/
- Auth: Bearer (ADMIN only)
- Body: `{ "trust_tier": 1|2|3 }`
- Response 200: `{ "id", "status": "APPROVED", "tx_hash" }`
- Side effect: triggers on-chain `approveIssuer()`
- Errors: 403 (not admin), 409 (already reviewed)

### POST /institutions/{id}/reject/
- Auth: Bearer (ADMIN only)
- Body: `{ "reason" }`
- Response 200: `{ "id", "status": "REJECTED" }`

---

## Issuers

### GET /issuers/status/
- Auth: Bearer (ISSUER)
- Response 200: `{ "institution_status", "wallet_address", "trust_tier" }`

### GET /issuers/{institution_id}/wallet/
- Auth: Bearer (ADMIN or the institution's own ISSUER users)
- Response 200: `{ "wallet_address", "is_whitelisted_onchain" }`

---

## Credentials

### POST /credentials/issue/
- Auth: Bearer (ISSUER, institution must be status=APPROVED)
- Body: `{ "student_email" or "student_id", "credential_type", "title", "issue_date", }` (multipart)
- Response 201: `{ "id", "status": "PENDING" → "ACTIVE" once confirmed, "tx_hash", "document_hash", "ipfs_cid" }`
- Errors: 403 (issuer not approved), 400 (validation)

### POST /credentials/issue-batch/
- Auth: Bearer (ISSUER, approved institution)
- Body: `{ "csv_file": <file>, "documents": [<file>,...] }` (multipart) 
— CSV columns: `student_email, credential_type, title, issue_date`
- Response 202: `{ "batch_id", "total": n, "status": "PROCESSING" }`

### GET /credentials/issue-batch/{batch_id}/status/
- Auth: Bearer (ISSUER, owner of the batch)
- Response 200: `{ "batch_id", "processed", "total", "failures": [ { "row", "reason" } ] }`

### GET /credentials/ (list)
- Auth: Bearer — STUDENT sees own; ISSUER sees ones they issued; ADMIN sees all
- Query params: `status`, `institution_id`, `student_id`
- Response 200: paginated list

### GET /credentials/{id}/
- Auth: Bearer (owner student, issuing institution, or ADMIN)
- Response 200: full credential record

### POST /credentials/{id}/revoke/
- Auth: Bearer (ISSUER who issued it, or ADMIN)
- Body: `{ "reason" }`
- Response 200: `{ "id", "status": "REVOKED", "tx_hash" }`
- Errors: 403 (not the issuer), 409 (already revoked)

---

## Verification

### GET /verify/{credential_id}/
- Auth: none (public)
- Response 200: `{ "result": "VALID"|"REVOKED"|"INVALID"|"NOT_FOUND", "credential_type", "title", "institution_name", "issue_date", "issuer_trust_tier" }` (only permitted fields, per any active `CredentialShare` scoping)
- Rate-limited to prevent enumeration abuse.

### POST /verify/upload/
- Auth: none (public)
- Body: `{ "document": <file>, "credential_id" }` (multipart) — recomputes hash and compares
- Response 200: `{ "result", "hash_match": true|false }`

### GET /verify/history/{credential_id}/
- Auth: Bearer (owner student, issuing institution, or ADMIN)
- Response 200: list of `VerificationRecord`

---

## Student

### GET /student/credentials/
- Auth: Bearer (STUDENT)
- Response 200: list of own credentials

### POST /student/credentials/{id}/share/
- Auth: Bearer (STUDENT, owner)
- Body: `{ "visible_fields": [...], "expires_at" (optional) }`
- Response 201: `{ "share_token", "public_url", "qr_code_url" }`

### GET /student/profile/public/{student_id}/
- Auth: none (public, only if `public_profile_enabled=true`)
- Response 200: student's public career profile (name, active credentials marked shareable)

---

## Recruiter

### GET /recruiter/profile/
- Auth: Bearer (RECRUITER)
- Response 200: recruiter profile

### GET /recruiter/verify/{credential_id}/
- Alias of `/verify/{credential_id}/`, logs `verifier` on the `VerificationRecord` when authenticated.

---

## Standard Error Codes

| HTTP | code | Meaning |
|---|---|---|
| 400 | VALIDATION_ERROR | Bad input |
| 401 | UNAUTHENTICATED | Missing/invalid token |
| 403 | FORBIDDEN | Authenticated but not permitted |
| 404 | NOT_FOUND | Resource does not exist |
| 409 | CONFLICT | State conflict (duplicate, already reviewed, already revoked) |
| 429 | RATE_LIMITED | Too many requests |
| 502 | BLOCKCHAIN_ERROR | On-chain call failed/timed out |
