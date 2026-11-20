# Authentication design

## Flow

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as API
  participant D as PostgreSQL
  B->>A: POST /api/auth/login {email, password}
  A->>A: rate limit (per account + per IP)
  A->>D: SELECT user; Argon2id verify (dummy hash if no such user)
  A->>D: INSERT refresh_tokens(sha256(token), family_id, +14d); INSERT audit_log
  A-->>B: {access_token (15 min)} + Set-Cookie gv_refresh (HttpOnly) + __Host-gv_csrf
  Note over B: access token kept in JS memory only
  B->>A: GET /api/users/me (Authorization: Bearer ...)
  A->>D: user by id, not deleted (role read from DB, never from the token)
  B->>A: POST /api/auth/refresh (cookie + X-CSRF-Token)
  A->>D: SELECT ... FOR UPDATE by sha256(token)
  alt token already rotated (reuse)
    A->>D: revoke entire family; audit auth.refresh_reuse_detected
    A-->>B: 401 + cookies cleared
  else valid
    A->>D: revoke old, insert new (same family)
    A-->>B: new access token + rotated cookies
  end
```

## Controls

| Threat | Control | Verified by |
|---|---|---|
| Password cracking after a DB leak | Argon2id (RFC 9106 profile), unique salt per hash; DB `CHECK` refuses non-Argon2id values | `test_argon2id_hash_and_verify`, `test_user_password_must_be_argon2id` |
| Weak or breached passwords | 12–128 chars; 30,492 breached passwords (12+ chars) rejected; repetitive and email-containing passwords rejected (NIST SP 800-63B: no composition rules) | `test_password_policy`, `test_password_must_not_contain_email` |
| Online guessing / credential stuffing | Failed logins limited to 5 per account and 20 per IP per 15 min; registrations 10 per IP per hour; `429` + `Retry-After` | `test_login_rate_limited_per_account`, `test_register_is_rate_limited_per_client` |
| User enumeration | Identical login failure for unknown email and wrong password; unknown email still runs an Argon2 verify (timing parity); registration returns the same `202` whether or not the email exists, and hashes the password either way | `test_login_failure_is_generic`, `test_unknown_email_still_runs_argon2`, `test_duplicate_registration_is_indistinguishable` |
| Mass assignment | `extra="forbid"` on every request model: `{"role": "admin"}` at registration → 422 | `test_register_rejects_extra_fields_mass_assignment` |
| JWT forgery / confusion | HS256 pinned (`alg=none` and algorithm switching rejected); 32+ char secret enforced at start-up; `exp`, `nbf`, `iat`, `iss`, `aud`, `sub` required; `typ=access` | `test_rejects_alg_none_token`, `test_rejects_invalid_claims_even_with_valid_signature`, `test_weak_jwt_secrets_refuse_to_start` |
| Privilege via token claims | The token carries only the user id. Role is read from the DB on every request, so a forged `role` claim does nothing and demotion is immediate | `test_role_claim_in_token_is_ignored` |
| Stolen refresh token | 256-bit opaque token, stored only as SHA-256; rotated on every use; reuse of a rotated token revokes the whole family | `test_refresh_tokens_are_stored_hashed`, `test_refresh_token_reuse_revokes_whole_family` |
| Deleted account still active | Access tokens re-check `deleted_at`; refresh fails for deleted users | `test_token_for_deleted_user_is_rejected` |
| Secrets in error responses | Custom 422 handler drops the submitted `input` (FastAPI echoes it by default, which would include a rejected password) | `test_password_policy` asserts the password is not in the response |
| Secrets in the audit trail | Audit rows hold only action, actor/target ids, IP, user agent. Attempted email addresses are not stored, because a password is often typed into the email field | `test_auth_events_are_audited_without_secrets` |

## Authorization

| Rule | Implementation | Verified by |
|---|---|---|
| Identity only from credentials | `get_current_user` (token + live DB row); self-service routes have no user id in path or body | `test_account_endpoints_require_authentication` |
| Property-level authz (API3) | `UserUpdateIn` accepts only `display_name` (`extra="forbid"`) | `test_update_rejects_protected_or_invalid_fields` |
| Function-level authz (API5) | `require_admin` on the admin **router**, so new routes inherit it; role read from DB | `test_admin_routes_reject_ordinary_users`, `test_every_admin_route_is_protected` |
| No admin lock-out | admins cannot change their own role; the last admin cannot delete their account | `test_admin_cannot_change_own_role`, `test_last_admin_cannot_delete_account` |
| First admin | operator CLI `app.manage promote-admin` (needs server access), audited with a null actor | `test_bootstrap_promotion_is_audited` |
| Accountability | role changes, exports, deletions and audit-log viewing are audited | `test_role_change_takes_effect_immediately_and_is_audited`, `test_audit_view_filters_and_is_itself_audited` |

## Account deletion and export

- **Delete** (`DELETE /api/users/me`) requires re-entering the password, rate-limited like
  login, so a stolen access token alone cannot erase an account. In one transaction:
  - favourites, their shares and photos, shares received and refresh tokens are **deleted**;
  - the user row is **anonymised**: email becomes `deleted-<id>@invalid`, name becomes
    "Deleted user", the password hash becomes unusable, and `deleted_at` is set;
  - audit rows are **retained** as security evidence. They contain no name, email or content.
  The email address can be registered again immediately.
- **Export** (`GET /api/users/me/export`) returns profile, favourites with exact coordinates and
  notes (the user's own data), shares, photo metadata, sessions and the user's own activity.
  Secrets are excluded (password hash, token hashes), and so are other people's personal
  information: share recipients appear by display name only.

## Token storage: memory + HttpOnly cookie (decision)

| Option | XSS impact | CSRF exposure | Verdict |
|---|---|---|---|
| Both tokens in `localStorage` | Script can read and **exfiltrate** both; the attacker keeps access after the tab closes | none | Rejected |
| Both tokens in cookies (cookie session) | Script cannot read the tokens | **every** endpoint needs CSRF protection | Rejected: large CSRF surface |
| **Access token in memory, refresh token in HttpOnly cookie** | Script can use the access token while the page is open (max 15 min) but can never read the refresh token | only `/refresh` and `/logout` use the cookie, and both require a CSRF header | **Chosen** |

Cookie attributes:
- `gv_refresh`: `HttpOnly; Secure; SameSite=Strict; Path=/api/auth`. It is sent only to auth endpoints.
- `__Host-gv_csrf`: `Secure; SameSite=Strict; Path=/`. JS-readable on purpose. The `__Host-` prefix forbids a `Domain` attribute, so a sibling subdomain cannot plant it.

Refresh and logout require `X-CSRF-Token` to equal that cookie (double-submit, constant-time compare). Other sites cannot read the cookie, so they cannot forge the header.

Browsers treat `http://127.0.0.1` and `http://localhost` as secure contexts, so `Secure` cookies work in local development. In AWS the app is served over HTTPS.

## Residual risks (accepted, documented)

- **XSS can still act as the user** while the page is open, using the in-memory access token.
  Mitigations: `textContent`-only rendering, no inline script, and a strict CSP (milestone 9).
  Tokens are short-lived.
- **Concurrent refresh race.** Two tabs refreshing the same token at the same instant: the second one looks like reuse and logs the session out. This is the safe failure direction.
- **The rate limiter is per process.** It is correct for the single-worker deployment, and is noted in code with its upgrade path.
- **No email verification.** No mail service is in scope. Registration does not prove ownership of the address, but it also reveals nothing about whether an address is registered.
