# Architecture

## High-Level Architecture

```
React.js (Tailwind, ethers.js)
        ↓  REST (JSON, JWT)
Django REST Framework
        ↓
SQLite (off-chain data of record)
        ↓
Blockchain Service (web3.py)
        ↓
Ethereum-compatible Network
        ↓
Solidity Smart Contract (issuer whitelist + credential registry)
```

Off-chain document files (certificate PDFs) are stored on IPFS; only the resulting content hash and CID reference are recorded on-chain / in the database.

## Component Breakdown

### Frontend (React)
- Role-based dashboards: Admin, Institution/Issuer, Student, Recruiter.
- Calls Django REST API for all data operations.
- Uses ethers.js only for: (a) connecting a wallet (MetaMask) for the institution to sign an issuer-registration message, and (b) optional direct read-only verification calls to the contract for public verification pages that should work even if the backend is briefly down.
- Never holds or uses a private key belonging to the platform.

### Backend (Django + DRF)
- Owns all business logic and authorization decisions.
- Apps: `accounts`, `institutions`, `credentials`, `verification`, `recruiters`, `blockchain`.
- The `blockchain` app wraps web3.py calls (whitelist an issuer, issue/revoke a credential, read verification status) so no other app talks to web3.py directly.

### Database (SQLite)
- System of record for everything **except** the three facts stored on-chain (hash, issuer address, revocation flag). See `DATABASE_SCHEMA.md`.

### Blockchain (Solidity)
- Minimal, auditable contract: issuer whitelist mapping + credential registry mapping + revoke function + events. See `BLOCKCHAIN_SPECIFICATION.md`.

## Authentication Flow

```
User submits email/password
        ↓
Django validates credentials
        ↓
Issues JWT access + refresh token
        ↓
Frontend stores tokens (memory + httpOnly-preferred refresh)
        ↓
Access token sent as Bearer header on each request
        ↓
Django validates token + role on every protected endpoint
```

## Issuer Approval Flow

```
Institution submits registration + KYC documents
        ↓
Status = PENDING (stored in Django DB only — no chain interaction yet)
        ↓
Admin reviews documents in Admin Dashboard
        ↓
Admin approves
        ↓
Django backend calls blockchain.approveIssuer(wallet_address)
        ↓
Contract emits IssuerApproved event
        ↓
Institution status = APPROVED; "Issue Credential" UI unlocks
```

Rejection path: status = REJECTED, no chain interaction occurs, institution is notified with a reason.

## Credential Issuance Flow

```
Approved issuer submits credential data (single or CSV batch)
        ↓
Backend generates/receives certificate document
        ↓
Backend computes SHA-256 hash of the document
        ↓
Backend uploads document to IPFS → receives CID
        ↓
Backend calls blockchain.issueCredential(credentialId, hash, issuerAddress)
   (contract enforces onlyApprovedIssuer)
        ↓
Contract emits CredentialIssued event
        ↓
Backend stores Credential row (status=ACTIVE, tx hash, CID, on-chain hash)
        ↓
Student is notified; credential appears in their dashboard
```

## Credential Verification Flow

```
Verifier submits credential ID or scans QR
        ↓
Backend/frontend fetches credential record + on-chain status
        ↓
Backend recomputes document hash (if a file was provided) and compares to on-chain hash
        ↓
Backend checks issuer is/was whitelisted at issuance time
        ↓
Backend checks revocation status on-chain
        ↓
Result returned: VALID / REVOKED / INVALID / NOT_FOUND
```

## Credential Revocation Flow

```
Issuer selects a credential they issued → Revoke
        ↓
Backend verifies requester is the original issuer (or Admin, per policy)
        ↓
Backend calls blockchain.revokeCredential(credentialId)
        ↓
Contract sets revoked=true, emits CredentialRevoked event
        ↓
Backend updates Credential.status = REVOKED
        ↓
All future verifications show REVOKED, with the revocation timestamp
```

## Student Sharing Flow

```
Student selects a credential → "Generate Share Link / QR"
        ↓
Backend creates a CredentialShare record (optionally scoped: full record or limited fields)
        ↓
Backend returns a public verification URL + QR code
        ↓
Recruiter opens link → hits public verification endpoint → sees permitted fields only
```

## Recruiter Verification Flow

```
Recruiter opens shared link or scans QR, or manually enters a credential ID
        ↓
Public verification endpoint returns status + permitted credential fields
        ↓
Recruiter can additionally view the student's public career profile, if the student has made one visible
```

## Data Flow: On-Chain vs Off-Chain (summary)

| Data | Location |
|---|---|
| Credential ID, document hash, issuer address, timestamp, revoked flag | On-chain |
| Full certificate PDF | IPFS (off-chain, content-addressed) |
| Student name, email, phone, marksheet detail, institution KYC docs | Django DB (off-chain, access-controlled) |
| Issuer approval status/history | Django DB (off-chain) + whitelist mapping (on-chain) |

See `SECURITY.md` for the reasoning behind this split.

## MetaMask / Wallet Integration Scope

MetaMask is used only to **obtain and prove control of a wallet address on the client side** — it is never used to sign any privileged platform transaction. All privileged on-chain writes (issuer approval, credential issuance, revocation) are signed server-side by Django using `PLATFORM_ADMIN_PRIVATE_KEY` or the relevant issuer flow, per the "Django is the only component allowed to write to the blockchain" rule in `AGENTS.md` Section 7.

### Where MetaMask IS used

| Use case | What happens |
|---|---|
| Institution registration | Institution connects MetaMask on the React frontend; the connected address is submitted as `wallet_address` in the registration form |
| Local development/testing | A Ganache test account's private key is imported into MetaMask so transactions and balances are visible during development and demos |
| (Optional, Phase 11) Student wallet linking | A student may optionally connect a wallet to populate `StudentProfile.wallet_address` |

### Where MetaMask is NOT used

- **Admin approval of an institution** — signed by the backend's own `PLATFORM_ADMIN_PRIVATE_KEY`, not by an admin's MetaMask popup.
- **Credential issuance/revocation** — signed by the backend on the issuer's behalf using platform-managed transaction submission, not a live MetaMask signature per action.
- **Verification** — a public, unauthenticated read call; no wallet needed at all.

### Known Limitation: Address Submission vs. Proven Ownership

The current design (Option A below) accepts a wallet address at registration without cryptographically verifying the institution actually controls it. This is called out explicitly rather than left implicit, since it's a legitimate gap to be aware of:

| Option | Description | Status |
|---|---|---|
| **A — Address only (current)** | Institution submits a wallet address; no proof of ownership required at registration time | Implemented |
| **B — Signed challenge (Sign-In with Ethereum / EIP-4191)** | Backend issues a challenge message, institution signs it with MetaMask, backend verifies the signature recovers to the claimed address before accepting registration | Future scope |

Option B closes the gap where someone could submit a wallet address they don't actually control. It is not required for the prototype's core demonstration (issuer whitelisting still fully prevents an *unapproved* address from issuing credentials, regardless of whether address ownership was proven at registration) but should be implemented before any real-world deployment.

## Custodial Wallet Model (Institution Signing Keys)

To ensure secure automated credential issuance and prevent raw private key exposure over HTTP (such as via request bodies or custom headers), the platform implements **Model A: Custodial Wallets Encrypted at Rest**.

### Architecture & Key Lifecycle
1. **Wallet Generation:** When an Admin approves a pending institution (`POST /institutions/{id}/approve/`), the backend generates a dedicated Ethereum keypair (`w3.eth.account.create()`) if one does not already exist.
2. **Encryption at Rest:** The raw private key is encrypted immediately using Fernet symmetric encryption (`cryptography.fernet.Fernet`), keyed by `WALLET_ENCRYPTION_KEY` from environment variables (completely separate from `DJANGO_SECRET_KEY`). The ciphertext is stored in `Institution.encrypted_private_key`. The raw private key is never written to disk or database.
3. **Address Roles:**
   - `Institution.registered_wallet_address`: Preserves the self-reported MetaMask address submitted during initial institution registration for provenance, audit, and contact records.
   - `Institution.wallet_address`: Replaced with the newly generated custodial wallet address. This is the exact address passed to the smart contract's `approveIssuer()` function and recorded in the on-chain authorized issuer whitelist.
4. **In-Memory Decryption & Signing:** During credential issuance (`issueCredential`, `batchIssueCredentials`) or revocation (`revokeCredential`), the backend looks up the institution by `wallet_address`, decrypts the private key strictly in-memory, signs the transaction, and broadcasts the raw signed transaction. The decrypted key is never logged, never returned via API responses, and never accepted from client requests.

### Tradeoffs & Production Alternatives
- **Deliberate Tradeoff:** The custodial design requires institutions to trust the platform backend to custody and sign on their behalf without key leakage or misuse. This is an explicit, documented prototype design decision.
- **Production Non-Custodial Alternative:** In a production release, the platform can migrate to non-custodial signing:
  - The institution signs issuance payloads or EIP-712 typed data directly within their browser via MetaMask.
  - The platform backend serves purely as a gasless relayer or forwarder (ERC-2771 meta-transactions or smart contract delegated-call pattern), eliminating server-side custodial key storage entirely.
