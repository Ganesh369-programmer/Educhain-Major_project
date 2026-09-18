# Feature Roadmap

Each phase lists objective, features, and work by layer. Phases are meant to be built roughly in order, since later phases depend on earlier ones (e.g., you cannot issue a credential before an issuer can be whitelisted).

## Phase 1 — Project Setup
- **Objective:** working skeleton for all three layers.
- **Backend:** Django project + apps scaffolded, DRF installed, SQLite configured, `.env` handling.
- **Frontend:** React app (Vite), Tailwind configured, routing skeleton, Axios client.
- **Blockchain:** Hardhat project initialized, local network running.
- **Testing:** CI/local scripts can run `manage.py check`, `npm run build`, `npx hardhat compile` successfully.

## Phase 2 — Authentication and Users
- **Objective:** register/login for all roles.
- **Backend:** `accounts` app — `User` model, JWT endpoints, role-based permission classes.
- **Frontend:** login/register pages, `AuthContext`, protected route wrapper.
- **Testing:** auth flow tests (register, login, refresh, role-based 403s).

## Phase 3 — Institution Onboarding
- **Objective:** institutions can register and upload KYC documents.
- **Backend:** `institutions` app — `Institution` model, registration endpoint, file upload handling.
- **Frontend:** institution registration form (multi-step: basic info → documents → wallet connect).
- **Database:** `Institution` table live.

## Phase 4 — Admin Institution Approval
- **Objective:** admin can review and approve/reject institutions.
- **Backend:** approve/reject endpoints, notification on decision.
- **Frontend:** Admin dashboard — pending applications queue, document preview, approve/reject actions.
- **Dependencies:** Phase 3.

## Phase 5 — Issuer Authorization (On-Chain Whitelist)
- **Objective:** approval actually grants on-chain issuance rights.
- **Blockchain:** deploy `CredentialPlatform` contract (issuer + credential registry) to local/testnet.
- **Backend:** `blockchain` app wrapper (`approve_issuer()`), wired into the institution-approval flow.
- **Testing:** Hardhat tests for `approveIssuer`/`onlyApprovedIssuer`; backend test that approval triggers the correct on-chain call (mocked).

## Phase 6 — Credential Database
- **Objective:** off-chain credential model ready before on-chain issuance is wired up.
- **Backend:** `credentials` app — `Credential`, `CredentialShare` models, serializers.
- **Database:** migrations for `Credential`-related tables.

## Phase 7 — Smart Contract (Credential Registry)
- **Objective:** issuance/revocation functions complete and tested.
- **Blockchain:** `issueCredential`, `batchIssueCredentials`, `revokeCredential`, `verifyCredential` implemented and unit-tested (see `BLOCKCHAIN_SPECIFICATION.md`).

## Phase 8 — Blockchain Credential Issuance
- **Objective:** end-to-end issuance (single credential) works.
- **Backend:** document hashing, IPFS upload, `blockchain.issue_credential()` call, `Credential` row lifecycle (PENDING → ACTIVE).
- **Frontend:** issuer "Issue Credential" form.
- **Testing:** integration test against local Hardhat node.

## Phase 9 — Credential Verification
- **Objective:** public verification works end-to-end.
- **Backend:** `verification` app — public endpoint, hash comparison, `VerificationRecord` logging.
- **Frontend:** public verification page (enter ID or scan QR), result display (VALID/REVOKED/INVALID/NOT_FOUND).

## Phase 10 — Credential Revocation
- **Objective:** issuers/admin can revoke, and verification reflects it.
- **Backend:** revoke endpoint, on-chain call, status update.
- **Frontend:** "Revoke" action in issuer dashboard with reason field.

## Phase 11 — Student Credential Dashboard
- **Objective:** students can see and manage their own credentials.
- **Frontend:** student dashboard listing credentials with status badges.
- **Backend:** `/student/credentials/` endpoint.

## Phase 12 — Credential Sharing and QR Verification
- **Objective:** selective sharing works end-to-end.
- **Backend:** `CredentialShare` creation endpoint, scoped public verification response.
- **Frontend:** "Generate Share Link/QR" UI, QR code rendering.

## Phase 13 — Recruiter / Career Platform
- **Objective:** recruiters can verify and view public career profiles.
- **Backend:** `recruiters` app, public profile endpoint respecting `public_profile_enabled`.
- **Frontend:** recruiter dashboard, public profile page.

## Phase 14 — Security Hardening
- **Objective:** close gaps before demo/deployment.
- **Backend:** rate limiting on auth/verification endpoints, review all permission classes against `USER_ROLES_AND_PERMISSIONS.md`, secret/env audit.
- **Blockchain:** re-check access-control modifiers, consider a testnet audit checklist.

## Phase 15 — Testing and Deployment (Demo Readiness)
- **Objective:** stable, demoable build.
- **All layers:** run full test suites, fix regressions, prepare seed/demo data (a few pre-approved institutions, sample credentials) for a reliable live demo.
- **Docs:** final pass to make sure `docs/` matches the actual implementation (see `DEVELOPMENT_RULES.md` rule 17).

## Dependency Summary

```
Phase 1 → 2 → 3 → 4 → 5 → (6,7 can run in parallel) → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15
```
Phases 6 and 7 (credential DB model, smart contract functions) have no dependency on each other and can be built in parallel once Phase 5 (whitelist) is done.
