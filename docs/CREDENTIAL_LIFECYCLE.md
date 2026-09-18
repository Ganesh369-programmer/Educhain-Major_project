# Credential Lifecycle

## States

```
PENDING   — issuance transaction submitted, waiting for on-chain confirmation
ACTIVE    — confirmed on-chain, valid and verifiable
REVOKED   — issuer (or admin) revoked it; permanently terminal
INVALID   — not a stored state; a verification-time result when a provided document's
            hash does not match the on-chain record (tamper detected)
```

Only `PENDING`, `ACTIVE`, and `REVOKED` are persisted on the `Credential` model. `INVALID` and `NOT_FOUND` are verification **results**, not stored statuses — they describe the outcome of a specific verification attempt, not the credential record itself.

## Full Lifecycle Diagram

```
Institution approved
        ↓
Institution becomes an authorized issuer (on-chain whitelist)
        ↓
Issuer creates a credential (single or as part of a batch)
        ↓
Backend computes document hash → uploads to IPFS → submits on-chain transaction
        ↓
Credential.status = PENDING
        ↓
Transaction confirmed on-chain (CredentialIssued event observed)
        ↓
Credential.status = ACTIVE
        ↓
Student sees it in their dashboard, can share it (CredentialShare + QR)
        ↓
Recruiter/verifier checks it → result computed at verification time
        ↓
Credential remains ACTIVE indefinitely, unless revoked
        ↓
   (optional) Issuer or Admin revokes it, with a reason
        ↓
Credential.status = REVOKED (terminal — no path back to ACTIVE)
```

## State Transition Table

| From | To | Trigger | Who |
|---|---|---|---|
| (none) | PENDING | Issuance request accepted, tx submitted | Issuer (approved institution) |
| PENDING | ACTIVE | Tx confirmed on-chain | System (event listener/confirmation check) |
| PENDING | (failed, not persisted as a lifecycle state) | Tx reverted/failed | System — record marked failed in `BlockchainTransaction`, `Credential` row not created or marked internally errored |
| ACTIVE | REVOKED | Explicit revoke action | Issuer (original) or Admin (override) |
| REVOKED | — | No further transitions | — |

## Verification-Time Results (not stored states)

| Result | Meaning |
|---|---|
| VALID | Credential exists, hash matches, not revoked |
| REVOKED | Credential exists but has been revoked |
| INVALID | A hash mismatch was detected against a provided document |
| NOT_FOUND | No credential exists for the given ID |

## Why Keep the State List Minimal

Extra states (e.g., "EXPIRED", "SUSPENDED") were considered but are out of scope for the initial build — only add a new state if a real requirement needs it, and update this file plus `DATABASE_SCHEMA.md` and `BLOCKCHAIN_SPECIFICATION.md` together when you do, so they never drift out of sync.
