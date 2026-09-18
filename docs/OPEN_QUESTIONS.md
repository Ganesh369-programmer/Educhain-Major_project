# Open Questions

Decisions that were ambiguous in the original requirements and were resolved with a reasonable default for the prototype. Revisit these before treating the project as production-ready, and update this file whenever one is resolved differently.

## 1. Historical vs. Current Issuer Whitelist Check at Verification Time

**Question:** If a credential was issued while an institution was whitelisted, but the institution is later revoked (e.g., found fraudulent), should old credentials from that issuer immediately show as untrustworthy, or keep their original valid status with a separate "issuer since revoked" warning?

**Default used:** Verification checks *current* whitelist status. If the issuer has since been revoked, verification result includes an explicit warning ("issuer's authorization has since been revoked") alongside whatever the credential's own status is, rather than silently marking every past credential REVOKED. This matches the fraud-prevention discussion earlier — revocation of an issuer should flag their past output, not necessarily erase it, since some of those credentials may have been legitimately issued before the fraud began.

## 2. Refresh Token Storage Strategy

**Question:** httpOnly cookie (more secure, more backend setup) vs. in-memory storage (simpler, but lost on tab close) for the refresh token.

**Default used:** In-memory storage documented as an accepted trade-off for the academic prototype's timeline (see `AUTHENTICATION.md`). Revisit if the project moves toward a real deployment.

## 3. Trust Tier Assignment Automation

**Question:** Should trust tier (1/2/3) be fully automated from the registration_type/documents, or always require a manual admin decision even for obvious cases (e.g., a UGC-listed university)?

**Default used:** Automated pre-check suggests a tier based on `institution_type` and document format validation, but the Admin always makes the final tier decision at approval time (not fully automatic) — keeps a human in the loop for the prototype.

## 4. Credential ID Generation

**Question:** Should `credentialId` (the on-chain bytes32 key) be a hash of student+institution+credential-type+date, a random UUID converted to bytes32, or something else?

**Default used:** A deterministic hash (e.g., keccak256 of `student_id + institution_id + credential_type + issue_date + a random nonce`) so IDs are unpredictable (nonce) but reproducible for debugging given the inputs. Finalize the exact formula when implementing Phase 7/8.

## 5. Batch Issuance Partial Failure Handling

**Question:** If 3 out of 500 rows in a bulk CSV upload fail (bad data, duplicate hash), should the whole batch transaction fail, or should valid rows still be issued and failures reported separately?

**Default used:** Per `API_SPECIFICATION.md`'s `/credentials/issue-batch/status/` design, valid rows are issued and failures are reported individually — avoids one bad row blocking an entire graduating class's issuance. Confirm this matches the actual demo/report expectations before building Phase 8.

## 6. Admin Credential Revocation Override — Reason Requirement

**Question:** Should Admin-initiated revocation (overriding a normal issuer) require a mandatory, recorded reason, distinct from an issuer's own revocation reason?

**Default used:** Yes — mandatory reason field, logged distinctly, since this is a higher-trust override action (see `SECURITY.md` audit logging).
