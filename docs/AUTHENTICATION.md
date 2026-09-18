# Authentication

## Overview

JWT-based authentication using `djangorestframework-simplejwt` (or equivalent). Two tokens: short-lived **access token**, longer-lived **refresh token**.

## Roles

```
ADMIN
STUDENT
ISSUER
RECRUITER
```

A `User.role` is set at registration and is immutable through normal API usage (role changes require an Admin action, not a self-service endpoint).

## Registration

- `POST /auth/register/` — STUDENT, ISSUER, RECRUITER can self-register with `email` + `password` + `role`.
- ADMIN accounts are created only via Django management command / seed script — never through a public endpoint.
- ISSUER registration creates the `User` immediately, but the associated `Institution` starts at `status=PENDING` and has no issuance rights until Admin approval (see `USER_ROLES_AND_PERMISSIONS.md`).

## Login

- `POST /auth/login/` with `email` + `password`.
- On success: returns `access` (short-lived, e.g. 15–30 min) and `refresh` (longer-lived, e.g. 7 days) tokens.
- Passwords are hashed with Django's default PBKDF2/Argon2 hasher — never stored or logged in plaintext.

## Access Token

- Sent as `Authorization: Bearer <access>` on every protected request.
- Contains `user_id` and `role` claims (role is also re-checked against the DB on sensitive actions, not trusted purely from the token, to allow immediate effect of an Admin role/status change).

## Refresh Token

- Used against `POST /auth/refresh/` to obtain a new access token without re-entering a password.
- Rotated on each use; old refresh tokens are blacklisted (rotation + blacklist strategy) to reduce replay risk.

## Token Expiration

| Token | Suggested lifetime |
|---|---|
| Access | 15–30 minutes |
| Refresh | 7 days |

Configurable via `JWT_ACCESS_TOKEN_LIFETIME_MIN` / `JWT_REFRESH_TOKEN_LIFETIME_DAYS` env vars.

## Password Security

- Minimum length + complexity enforced server-side (Django's `AUTH_PASSWORD_VALIDATORS`).
- Never returned in any API response, never logged.

## Authentication Middleware

- DRF's `JWTAuthentication` class validates the access token on every request to a protected view.
- Public endpoints (`/auth/register/`, `/auth/login/`, `/auth/refresh/`, `/verify/{credential_id}/`, `/verify/upload/`, public profile/share links) are explicitly marked `permission_classes = [AllowAny]`.

## Role-Based Authorization

- Enforced via DRF permission classes (e.g., `IsAdmin`, `IsApprovedIssuer`, `IsOwnerStudent`) applied per view — never assumed from the frontend.
- See the full matrix in `USER_ROLES_AND_PERMISSIONS.md`.

## Protected API Endpoints

All endpoints under `/institutions/`, `/issuers/`, `/credentials/` (except the public verify routes), `/student/`, `/recruiter/`, and `/users/me/` require a valid access token. Role checks are layered on top per endpoint.

## Frontend Token Handling

- Access token kept in memory (React state/context), not `localStorage`, to reduce XSS exposure.
- Refresh token handling: prefer an httpOnly cookie set by the backend if the deployment setup allows it; if not feasible in the student project timeline, store in memory and require re-login on tab close as an accepted trade-off (document this trade-off in `OPEN_QUESTIONS.md` if chosen).
- Axios/fetch interceptor: on a 401 with an expired-access-token error code, silently call `/auth/refresh/` once, then retry the original request; on refresh failure, redirect to login.

## Logout

- `POST /auth/logout/` blacklists the given refresh token.
- Frontend clears in-memory tokens and redirects to login.

## Unauthorized Responses

| Situation | HTTP | code |
|---|---|---|
| No/invalid token | 401 | UNAUTHENTICATED |
| Valid token, wrong role/permission | 403 | FORBIDDEN |
| Expired access token | 401 | TOKEN_EXPIRED (frontend should attempt refresh) |
| Expired/blacklisted refresh token | 401 | REFRESH_INVALID (force re-login) |
