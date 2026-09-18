# Architecture

## High-Level Architecture

```
React.js (css, ethers.js)
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
