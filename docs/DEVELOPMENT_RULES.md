# Development Rules

These rules apply to every contributor — human or AI coding agent.

1. Read `AGENTS.md` before making any change.
2. Read the relevant file(s) under `docs/` before implementing a feature — don't guess at the contract, schema, or API shape.
3. Inspect existing code before creating new files — check whether a component, service, model, or serializer already does what you need.
4. Reuse existing components and services rather than duplicating logic.
5. Do not duplicate functionality across apps/modules.
6. Do not rename existing API endpoints, model fields, or smart contract functions without a strong, documented reason — and update the relevant `docs/` file in the same change.
7. Do not change database models unnecessarily; if you must, update `DATABASE_SCHEMA.md` in the same change.
8. Do not modify unrelated features while implementing a requested one.
9. Do not introduce a new library/dependency without a one-line justification for why the existing stack doesn't already cover the need.
10. Do not hardcode secrets — use environment variables per `AGENTS.md` Section 13.
11. Do not put blockchain private keys in frontend code, ever.
12. Do not store sensitive personal data on-chain — see `SECURITY.md`'s on-chain/off-chain table.
13. Validate all API input server-side, even if the frontend also validates.
14. Enforce authorization on the backend for every privileged action — never trust a frontend role check alone.
15. Never rely only on frontend role restrictions for security.
16. Write tests for important business logic (permission checks, issuance/revocation flow, whitelist enforcement).
17. Update documentation whenever the architecture, schema, API contract, or contract interface changes — stale docs are worse than no docs, since future agents will trust them.

## When a Requirement Is Ambiguous

Do not silently invent an important business decision (e.g., exact revocation authority, exact trust-tier thresholds). Instead, add it to `docs/OPEN_QUESTIONS.md` with the specific question and, if helpful, the options considered, and proceed with the most conservative/reversible interpretation in the meantime.

## When a Request Conflicts With Existing Documentation

Stop and surface the conflict rather than picking a side unilaterally. State what the docs currently say, what the new request implies, and ask which should win before making a structural change.
