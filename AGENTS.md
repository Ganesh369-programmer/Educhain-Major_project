# AGENTS.md — AI Coding Agent Context

This file is the **single source of truth** for any AI coding agent (or human developer) working on this repository. Read this file completely before writing or modifying any code.

## 1. What This Project Is

**Blockchain-Based Academic Credential Verification and Career Platform.**

It lets verified educational institutions issue tamper-proof digital academic credentials on a blockchain, lets students own and selectively share those credentials, and lets recruiters/employers instantly verify authenticity — while also building a verified career profile layer on top of the credentials.

## 2. Technology Stack (do not substitute without discussion)

| Layer | Technology |
|---|---|
| Frontend | React.js + Tailwind CSS |
| Backend | Django + Django REST Framework |
| Database | SQLite (development) |
| Blockchain | Ethereum-compatible network (testnet: Sepolia/Polygon Amoy) |
| Smart Contracts | Solidity |
| Blockchain integration | ethers.js (frontend), web3.py (backend) |
| Auth | JWT (access + refresh tokens) |
| Dev OS | Windows |

## 3. High-Level Architecture

```
React (client) → Django REST API → SQLite (off-chain data)
                       ↓
              Blockchain Service (web3.py)
                       ↓
        Ethereum-compatible Network (Solidity contract)
```

Django is the **only** component allowed to write to the blockchain (issuing/revoking/whitelisting). The frontend may read directly from the chain via ethers.js for verification-only calls, but never signs privileged transactions itself.

## 4. Component Responsibilities

- **React**: UI, forms, role-based routing, calling the Django REST API, displaying verification results, QR generation/scanning, MetaMask connect for wallet actions.
- **Django**: business logic, authentication, KYC/document storage, permission enforcement, orchestrating blockchain calls, off-chain database of record.
- **SQLite**: all off-chain data — users, institutions, KYC documents, student profiles, credential metadata, notifications.
- **Blockchain / Solidity**: issuer whitelist, credential hash registry, revocation status. Nothing else. See BLOCKCHAIN_SPECIFICATION.md.

## 5. API Communication Rules

- All frontend ↔ backend communication goes through the documented REST API in `docs/API_SPECIFICATION.md`. No ad-hoc endpoints.
- All responses are JSON. Errors follow a consistent `{ "detail": "...", "code": "..." }` shape.
- Pagination, filtering, and auth headers follow DRF conventions.

## 6. Authentication & Authorization Rules

- JWT access + refresh tokens (see `docs/AUTHENTICATION.md`).
- Roles: `ADMIN`, `STUDENT`, `ISSUER`, `RECRUITER`. See `docs/USER_ROLES_AND_PERMISSIONS.md` for the full matrix.
- **Authorization is always enforced server-side.** Frontend route guards are UX only, never a security boundary.

## 7. Blockchain Integration Rules

- Only wallet addresses approved by an Admin (via the whitelist flow) may issue credentials — enforced at two independent layers: a Django pre-check, and the smart contract's `onlyApprovedIssuer` modifier.
- Never store PII (name, email, phone, full marksheet) on-chain. Only a credential ID, a document hash, the issuer address, a timestamp, and status. See Section 2 of `docs/SECURITY.md`.
- Private keys for any platform-controlled wallet live only in backend environment variables — never in frontend code, never committed to the repo.

## 8. Security Rules (summary — full detail in docs/SECURITY.md)

- No secrets, API keys, or private keys hardcoded anywhere.
- All input validated server-side (DRF serializers), regardless of frontend validation.
- CORS locked to known frontend origins.
- Rate-limit auth and verification endpoints.

## 9. Coding & Naming Conventions

- Python: PEP8, snake_case for functions/variables, PascalCase for classes/models.
- React: PascalCase components, camelCase functions/variables, one component per file.
- Solidity: camelCase functions, PascalCase contracts/structs, events in PascalCase prefixed with a verb (e.g., `CredentialIssued`).
- Django apps are feature-scoped (`accounts`, `institutions`, `credentials`, `verification`, `recruiters`, `blockchain`) — do not mix concerns across apps.

## 10. Rules for Modifying Existing Code

- **Never blindly overwrite existing code.** Read the current implementation before changing it.
- Reuse existing components, services, models, and serializers before creating new ones.
- Do not rename existing API endpoints, model fields, or contract functions without a documented, strong reason — update `docs/` in the same change if you do.
- Do not refactor unrelated code while implementing a feature.
- Do not introduce a new library/dependency without a one-line justification.
- If a request conflicts with something in `docs/`, stop and surface the conflict instead of silently choosing an interpretation.

## 11. Testing Requirements

- Backend: unit tests for serializers, views, and permission logic (pytest / DRF test client).
- Smart contracts: Hardhat tests for issuer whitelist, issuance, revocation, and access-control failure cases.
- Frontend: at minimum, smoke tests for the auth flow and the verification page.

## 12. Standard Workflow for a New Feature

```
Understand requirement
        ↓
Read relevant documentation
        ↓
Inspect existing code
        ↓
Identify affected components
        ↓
Plan implementation
        ↓
Implement backend
        ↓
Test backend
        ↓
Implement frontend
        ↓
Test frontend
        ↓
Integrate blockchain if required
        ↓
Test complete feature
        ↓
Update documentation
```

## 13. Environment Variables (never commit real values — use `.env` + `.env.example`)

```
DJANGO_SECRET_KEY=
DEBUG=
ALLOWED_HOSTS=
DATABASE_URL=
JWT_SIGNING_KEY=
JWT_ACCESS_TOKEN_LIFETIME_MIN=
JWT_REFRESH_TOKEN_LIFETIME_DAYS=
BLOCKCHAIN_RPC_URL=
BLOCKCHAIN_CHAIN_ID=
CONTRACT_ADDRESS=
PLATFORM_ADMIN_PRIVATE_KEY=   # backend-only, used solely for admin-triggered on-chain calls
IPFS_API_URL=
IPFS_PROJECT_ID=
IPFS_PROJECT_SECRET=
CORS_ALLOWED_ORIGINS=
```

## 14. Documentation Index

See `docs/` for: `PROJECT_OVERVIEW.md`, `ARCHITECTURE.md`, `DATABASE_SCHEMA.md`, `API_SPECIFICATION.md`, `BLOCKCHAIN_SPECIFICATION.md`, `AUTHENTICATION.md`, `USER_ROLES_AND_PERMISSIONS.md`, `CREDENTIAL_LIFECYCLE.md`, `FRONTEND_GUIDELINES.md`, `BACKEND_GUIDELINES.md`, `SECURITY.md`, `DEVELOPMENT_RULES.md`, `FEATURE_ROADMAP.md`, `OPEN_QUESTIONS.md`.
