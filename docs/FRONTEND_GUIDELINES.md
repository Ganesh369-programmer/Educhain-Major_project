# Frontend Guidelines (React)

## Suggested Structure

```
frontend/
└── src/
    ├── components/     # reusable, presentational UI pieces
    ├── pages/          # route-level views (one per route)
    ├── layouts/         # shared page shells per role (AdminLayout, StudentLayout, ...)
    ├── services/        # API client wrappers (one file per backend resource)
    ├── hooks/            # custom hooks (useAuth, useCredential, ...)
    ├── context/          # AuthContext, etc.
    ├── utils/            # formatting, validation helpers
    ├── routes/           # route definitions + role-based guards
    └── assets/
```

## Component Structure

- One component per file, PascalCase filename matching the component name.
- Presentational components (in `components/`) should not call the API directly — they receive data via props and call handlers passed in.
- Page components (in `pages/`) own data-fetching via `services/` and `hooks/`, and compose presentational components.

## Services (API layer)

- One service module per backend resource, mirroring `API_SPECIFICATION.md` (e.g., `institutionService.js`, `credentialService.js`, `verificationService.js`).
- All services go through a single configured Axios instance (`utils/apiClient.js`) that attaches the auth header and handles token refresh centrally — do not create ad-hoc `fetch` calls scattered across components.

## Blockchain Services

- `services/blockchainService.js` wraps any direct ethers.js read calls (e.g., a public verification page reading `verifyCredential()` directly from the chain as a fallback/independent check).
- Wallet connection (MetaMask) logic lives here too — used only for institution wallet registration and any user-signed transactions, never for platform-privileged actions.

## Forms & Validation

- Use a form library (e.g., React Hook Form) with client-side validation mirroring, but never replacing, backend validation.
- Show field-level errors returned from the API (`VALIDATION_ERROR` responses) alongside client-side checks.

## Loading & Error States

- Every data-fetching page component handles three states explicitly: loading, error, and success/empty — no silent blank screens.
- Network/blockchain errors (`BLOCKCHAIN_ERROR`) get a distinct, user-understandable message (e.g., "Verification network is temporarily unavailable — try again shortly") rather than a generic error.

## Authentication State

- `AuthContext` holds the current user, role, and access token (in memory).
- `useAuth()` hook exposes `login`, `logout`, `refresh`, `currentUser`.

## Protected & Role-Based Routes

- A `<ProtectedRoute role="ADMIN">` wrapper (in `routes/`) redirects unauthenticated users to login and unauthorized-role users to a "not permitted" page.
- This is a UX convenience only — the backend independently enforces every permission (see `SECURITY.md`); never assume a hidden button means the action is actually blocked.

## Naming Conventions

- Components: `PascalCase.jsx` (e.g., `CredentialCard.jsx`)
- Hooks: `camelCase` starting with `use` (e.g., `useCredentials.js`)
- Services: `camelCase` ending in `Service` (e.g., `credentialService.js`)
- CSS: Tailwind utility classes directly in JSX; avoid ad-hoc custom CSS files unless a utility genuinely can't express something.

## State Management

- Local component state (`useState`) for page-local concerns.
- `Context` for cross-cutting concerns (auth, theme/role).
- No global state library (Redux, Zustand) unless a real cross-page shared-state need emerges — don't add one preemptively.

## Reusable Components (minimum set to plan for)

- `CredentialCard`, `StatusBadge` (ACTIVE/REVOKED/PENDING), `QRCodeDisplay`, `FileUpload`, `DataTable` (for admin/institution lists), `RoleGuard`.

## Do Not

- Do not put any private key or platform secret in frontend code or `.env` files that ship to the browser.
- Do not create unnecessary abstractions (e.g., a generic "widget factory") before a real need for it appears.
- Do not duplicate a service call's logic inline in a component — always go through `services/`.
