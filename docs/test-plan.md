# GeoVault security test plan

| | |
|---|---|
| Purpose | Authorised security assessment of GeoVault running on the developer's own machine |
| Standards | OWASP Web Security Testing Guide (WSTG v4.2), OWASP API Security Top 10 (2023), CVSS v3.1 |
| Threat model | [threat-model.md](threat-model.md). Every test case below traces to a threat there |
| Status | Secure-mode controls: **automated and passing** (295 tests in CI). Manual assessment: **planned**. Lab-mode assessment: blocked until milestone 11 exists |

## 1. Scope and rules of engagement

**In scope** (owned and operated by the developer):

| Target | Address |
|---|---|
| GeoVault API and UI, secure mode | `http://127.0.0.1:8010` (dev compose) |
| GeoServer (opt-in profile) | `http://127.0.0.1:8080/geoserver` |
| GeoVault lab mode (when built) | its own loopback port and lab database only |
| Local PostGIS | through the application and GeoServer only, never by direct network scanning |

**Out of scope, never contacted by any test tool:**
- City of Melbourne portal, data.gov.in, OpenCity, ISRO Bhuvan / NRSC;
- OpenStreetMap tile and Overpass servers, Wikimedia;
- GitHub, AWS-owned infrastructure, and any other third party.

Map tiles load in the browser during manual testing. Configure the proxy's scope to the
in-scope hosts only, so spidering and active scans never follow tile or CDN URLs.

**Rules:**
1. Only synthetic accounts (`@example.com`) and public or synthetic data. Never a real person's location.
2. Active scanning (ZAP active scan, sqlmap, ffuf) runs only against `127.0.0.1`, with the tool's
   scope locked to in-scope hosts before any scan starts.
3. Rate-limited endpoints (login, register, share) are expected to return `429`. Reaching the
   limit is a pass. Use fresh accounts or restart the API to reset counters; do not work around limits.
4. Stop and record if a test could affect anything outside the loopback interface.
5. Evidence (screenshots, requests) must redact passwords, tokens and session cookies before
   it leaves the machine. Findings never include working credentials.
6. Reset between runs: `docker compose down` (keeps data) or re-import the open data. Never use `down -v` on the dev project.

## 2. Test environment

| Item | Setup |
|---|---|
| Accounts | `alice@example.com` (user), `bob@example.com` (user, the second tenant for BOLA tests), `admin@example.com` promoted with `app.manage promote-admin` |
| Data | Real open data (3,295 places); each user has boxes in at least two cities, one with a photo, plus user shares and link shares |
| Tools | Burp Suite Community, OWASP ZAP, Postman, sqlmap, jwt_tool, ffuf, curl, browser devtools |
| Automated baseline | `docker compose -f compose.test.yml run --rm --build test` (must be green before and after manual testing); `py -3.10 geoserver/verify.py` |
| Logs | `docker compose logs -f api`: JSON lines with request IDs, used to correlate tests with server events |

## 3. Methodology

| Phase | WSTG areas | Main question |
|---|---|---|
| 1. Information gathering | WSTG-INFO | What is exposed: routes, versions, banners, docs, error formats? |
| 2. Configuration | WSTG-CONF | Are headers, CSP, CORS, HTTP methods and file serving locked down? |
| 3. Identity and authentication | WSTG-IDNT, WSTG-ATHN | Can accounts be enumerated, guessed or taken over? |
| 4. Session management | WSTG-SESS | Can tokens be forged, replayed, fixed or stolen through CSRF? |
| 5. Authorization | WSTG-ATHZ | Can one user reach another's objects or admin functions? |
| 6. Input validation | WSTG-INPV | Do any inputs reach SQL, HTML, file paths or parsers unsafely? |
| 7. Error handling and logging | WSTG-ERRH | Do errors or logs leak internals or secrets? |
| 8. Business logic | WSTG-BUSL | Can the sharing and cloaking flow be abused to recover exact locations? |
| 9. File upload | WSTG-BUSL-08/09 | Can uploads carry location metadata, script or exhaust resources? |
| 10. Client side | WSTG-CLNT | Are DOM sinks, storage and framing safe? |
| 11. GeoServer | WSTG-CONF, -ATHZ | Is anything other than public places reachable? |

Each case below names the expected secure behaviour and the automated test that already
asserts it. The manual pass tries to break the control in ways the automated test does not cover.

## 4. Test cases

**Status key:**
- **A** means an automated secure-mode test exists and passes in CI.
- **M** means a manual verification is planned.

### Authentication and session (API2)

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-AUTH-01 | ATHN-03 | Brute force one account | `429` with `Retry-After` after 5 failures; even the correct password is refused while locked | `test_login_rate_limited_per_account` | A, M |
| TC-AUTH-02 | IDNT-04 | Enumerate accounts through login, register and timing | Identical bodies and status codes; Argon2 verify runs for unknown emails | `test_login_failure_is_generic`, `test_unknown_email_still_runs_argon2`, `test_duplicate_registration_is_indistinguishable` | A, M |
| TC-AUTH-03 | ATHN-07 | Weak or breached passwords | Under 12 chars, breached, repetitive or email-containing passwords → 422, with no echo of the password | `test_password_policy`, `test_password_must_not_contain_email` | A |
| TC-AUTH-04 | SESS-01 | Token forgery and algorithm confusion (`none`, other key, wrong claims) | `401` for each | `test_rejects_alg_none_token`, `test_rejects_token_signed_with_other_key`, `test_rejects_invalid_claims_even_with_valid_signature` | A, M (jwt_tool) |
| TC-AUTH-05 | SESS-01 | Brute-force the signing secret offline from a captured token | Infeasible: the secret is enforced as long and random at start-up | `test_weak_jwt_secrets_refuse_to_start` | A, M |
| TC-AUTH-06 | SESS-02 | Cookie attributes | Refresh cookie HttpOnly, Secure, SameSite=Strict, `Path=/api/auth`; CSRF cookie `__Host-` | `test_login_sets_hardened_cookies` | A, M |
| TC-AUTH-07 | SESS-05 | CSRF on refresh and logout | `403` without a matching `X-CSRF-Token` | `test_refresh_requires_csrf_header`, `test_logout_requires_csrf` | A, M |
| TC-AUTH-08 | SESS-03 | Replay a rotated refresh token | `401`, and the whole session family is revoked | `test_refresh_token_reuse_revokes_whole_family` | A, M |
| TC-AUTH-09 | SESS-06 | Logout and account deletion invalidate sessions | Refresh fails after logout; access token fails after deletion | `test_logout_revokes_session`, `test_token_for_deleted_user_is_rejected` | A |

### Authorization (API1, API3, API5)

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-AUTHZ-01 | ATHZ-04 | As Bob, read, edit, delete or share Alice's favourite by id | `404`, identical to a non-existent id; Alice's data unchanged | `test_bola_other_users_favourite_is_404`, `test_bola_nonexistent_and_foreign_ids_are_indistinguishable` | A, M (Burp Autorize-style replay) |
| TC-AUTHZ-02 | ATHZ-04 | As Bob, access Alice's photo, shares or cloak preview | `404` | `test_other_users_cannot_touch_photo`, `test_cloak_preview_is_owner_only` | A, M |
| TC-AUTHZ-03 | ATHZ-04 | Revoke Alice's share via Bob's own favourite id | `404`; Alice's link still works | `test_bola_cannot_revoke_foreign_share_via_own_favourite` | A |
| TC-AUTHZ-04 | ATHZ-03 | Mass assignment: `role`, `email`, `id`, `owner_id`, `region` | `422`; stored values unchanged | `test_update_rejects_protected_or_invalid_fields`, `test_register_rejects_extra_fields_mass_assignment`, `test_create_validation` | A, M |
| TC-AUTHZ-05 | ATHZ-03 | Non-admin calls every admin route (and HTTP method variants) | `401` anonymous, `403` user | `test_admin_routes_reject_anonymous`, `test_admin_routes_reject_ordinary_users`, `test_every_admin_route_is_protected` | A, M |
| TC-AUTHZ-06 | ATHZ-03 | Forge a `role` claim in an otherwise valid token | Ignored; the role is read from the DB | `test_role_claim_in_token_is_ignored` | A |
| TC-AUTHZ-07 | BUSL | Share recipient tries to reach the underlying favourite | `404` on owner routes; only cloaked views available | `test_share_with_registered_user` | A |

### Data exposure and the cloaking flow (API3, business logic)

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-PRIV-01 | BUSL-01 | Shared link reveals only minimal, cloaked data | Exactly label, region, cloaked location, owner display name, dates, `has_photo` | `test_link_share_shows_only_cloaked_minimal_data` | A, M |
| TC-PRIV-02 | BUSL-07 | Average repeated shared views to recover the true point | Identical point on every request | `test_cloaking_is_deterministic_and_grid_aligned` | A, M |
| TC-PRIV-03 | BUSL-01 | Recover the exact location through the linked public place | No `place_id` or name in shared views | `test_shared_view_never_reveals_linked_place` | A |
| TC-PRIV-04 | BUSL-04 | Use a link after revocation, expiry, a switch to private, or owner deletion | `404` in every case | `test_revoked_link_is_404`, `test_expired_link_is_404`, `test_making_favourite_private_disables_existing_shares`, `test_owner_account_deletion_kills_links` | A, M |
| TC-PRIV-05 | — | Export contains only the caller's data and no secrets | No hashes, tokens or other users' emails | `test_export_contains_own_data_only_and_no_secrets` | A |
| TC-PRIV-06 | — | Account deletion actually erases personal data | Content deleted, identity anonymised, audit retained | `test_delete_erases_personal_data_and_keeps_anonymised_audit` | A |

### Input validation and injection

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-INJ-01 | INPV-05 | SQL injection in every query parameter (`q`, `category`, `region`, `bbox`, `lat`, `lon`, `radius_m`, audit `action`) | No error leakage and no behaviour change; typed parameters → 422 | `test_sql_injection_payloads_are_inert`, `test_input_validation_rejects`, `test_audit_filter_rejects_injection_shaped_input` | A, M (sqlmap, scoped) |
| TC-INJ-02 | INPV-05 | LIKE wildcard abuse in search | `%` and `_` matched literally | `test_like_wildcards_are_literal` | A |
| TC-INJ-03 | INPV-01 | Stored XSS through display name, label or note | Markup rejected in names; all values rendered as text | `test_register_rejects_markup_in_display_name`, `test_no_dangerous_dom_sinks` | A, M (browser) |
| TC-INJ-04 | INPV-12 | Header and log injection through `X-Request-ID` | Invalid IDs replaced | `test_request_id_generated_or_safely_propagated` | A |

### Resource consumption (API4) and file upload

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-RES-01 | BUSL-05 | Oversized radius, limit, offset or query length | `422` | `test_input_validation_rejects` | A |
| TC-RES-02 | BUSL-08 | Upload over 5 MB, or without `Content-Length` | `413` / `411` before the body is parsed | `test_oversized_declared_length_never_reaches_app`, `test_missing_content_length_never_reaches_app`, `test_upload_without_content_length_is_refused` | A, M |
| TC-RES-03 | BUSL-09 | Decompression bomb, polyglot, SVG/HTML or disguised file | `422`, audited; nothing stored | `test_rejects_non_images_and_bombs`, `test_decompression_bomb_rejected_before_decoding` | A, M |
| TC-RES-04 | BUSL-09 | GPS and camera metadata survives upload | Downloaded file has no EXIF, XMP or text chunks | `test_upload_strips_gps_end_to_end`, `test_photo_sanitise.py` | A, M (exiftool) |
| TC-RES-05 | BUSL-09 | Path traversal through the upload filename | Ignored; random UUID key inside the photo directory | `test_declared_content_type_and_filename_are_ignored` | A |
| TC-RES-06 | BUSL-05 | Bulk share creation or registration | `429` after 30 shares/h per user and 10 registrations/h per IP | `test_share_creation_is_rate_limited`, `test_register_is_rate_limited_per_client` | A |

### Configuration and inventory (API8, API9)

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-CONF-01 | CONF-12 | Security headers on every response (200/401/404/500) | CSP without inline or eval, `frame-ancestors 'none'`, nosniff, XFO, Referrer/Permissions/COOP/CORP | `test_security_headers_on_every_response` | A, M (ZAP passive) |
| TC-CONF-02 | CONF-07 | CORS from a foreign origin | No `Access-Control-Allow-*` headers | `test_no_cors_for_foreign_origins` | A, M |
| TC-CONF-03 | ERRH-01 | Force a server error | Generic JSON 500 with request ID; no traceback in the response | `test_unhandled_errors_are_generic_and_logged_safely` | A |
| TC-CONF-04 | INFO-02 | Server banner and docs | No `Server` header; `/docs` and `/openapi.json` 404 in production | `test_uvicorn_banner_and_raw_access_log_disabled`, `test_docs_disabled_in_production` | A, M |
| TC-CONF-05 | CONF-05 | Discover undocumented or legacy routes | Only the routes in the threat model inventory exist | — | M (ffuf, scoped to 127.0.0.1) |
| TC-CONF-06 | ERRH | Secrets and locations in logs | Redacted; no query strings in the access log | `test_logs_never_contain_secrets_or_locations` | A, M |

### GeoServer

| ID | WSTG | Objective | Expected (secure) | Automated | Status |
|---|---|---|---|---|---|
| TC-GEO-01 | CONF-04 | Default or anonymous admin access | `401` | `verify.py` | A (local) |
| TC-GEO-02 | ATHZ-02 | Reach a private table as a layer, including after an admin publishes it | `ExceptionReport` / no data | `verify.py`, `test_cannot_read_any_other_table` | A |
| TC-GEO-03 | — | WFS Transaction against public data | Rejected | `verify.py`, `test_every_transaction_is_read_only` | A |

## 5. Scoring and findings

- **Severity:** CVSS v3.1 base score, recording the vector string. Bands: Critical 9.0–10.0,
  High 7.0–8.9, Medium 4.0–6.9, Low 0.1–3.9, Informational 0.
- **Finding record:**
  - ID (`GV-YYYY-NNN`), title, OWASP API Top 10 / WSTG reference;
  - CVSS score and vector, severity, affected endpoint;
  - description, technical impact, business impact, reproduction steps (with secrets redacted), evidence;
  - remediation, the regression test added, and the retest result with date and commit.
- **Fix rule:** every confirmed finding gets a failing automated test first, then the fix, then
  a green CI run. The test stays in the suite permanently.
- **Report:** `docs/pentest-report.md`, structured as:
  1. executive summary (readable in two minutes);
  2. scope and rules;
  3. methodology;
  4. findings summary with a risk chart;
  5. detailed findings;
  6. remediation;
  7. retest;
  8. appendix.

## 6. Lab-mode assessment (after milestone 11)

The lab build removes specific controls (LAB-01 to LAB-08). For each LAB ID, the assessment:
1. Demonstrates the weakness against the lab instance on loopback, with evidence.
2. Scores it with CVSS v3.1.
3. Maps it to the secure control and the automated test in this plan that proves the fix.

The pentest report presents each as a finding with a "remediated in secure mode" retest.

## 7. Exit criteria

- Every case above is executed manually where marked **M**, with evidence.
- Every finding has a severity, a fix or a documented risk acceptance, and a regression test.
- The CI suite and `geoserver/verify.py` are green on the commit the report references.
