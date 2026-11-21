# Changelog

All notable changes to GeoVault. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Data and map (2026-11-21)
- **Far more places: 29,402 (was 3,295).** The OSM extract now covers every bus stop, BRT and
  bus station, railway station, halt and tram stop, plus hospitals, clinics, police and fire
  stations, schools, colleges, places of worship, community centres, cinemas, stadiums and post
  offices. Melbourne gains an OSM extract alongside City of Melbourne data; points within 40 m of
  a same-category CoM place are skipped as duplicates.
- Categories: `Transport` split into `Rail, metro and tram` and `Bus and BRT`; added
  `Community centre` and `Post office`.
- **Map key:** eight category groups, each with its own colour and shape (colour-blind-validated
  palette; shapes separate the hue pairs that are too close). The chips are the key and filter.
  `category` may now be repeated on `/api/places` and `/api/places/near` (max 20).
- Unsearched place lists use a stable hash order, so a capped page is an even spatial sample.
- Known gap documented: OSM has only ~185 Ahmedabad bus/BRT stops (AMTS runs ~4,000), and no
  open AMTS stop dataset exists.

### Fixed
- Switching city froze the tab: `setRegion` iterated the live listener `Set` while the hall view
  unsubscribed and re-subscribed, so the loop never ended. It now iterates a snapshot.

### Docs (2026-11-21)
- `docs/project-guide.md`: what GeoVault is, a screen-by-screen tour, how it works, milestone
  status, skills and knowledge applied, 30-second interview explanations, cheat-sheet and glossary.
- Stale facts corrected after a docs-vs-code audit: README status (3,295 places, lab mode the only
  unbuilt milestone), Bhuvan link-out covers both Indian cities, Ahmedabad's projection in the
  location-precision doc, PRODUCT.md counts. The suite stands at 295 tests (M12 and M13).

### Added — Milestone 13: threat model and test plan (2026-11-21)
- `docs/threat-model.md`: assets, threat actors, data-flow diagram with nine trust boundaries,
  attack-surface inventory, STRIDE per element (API, browser, DB, GeoServer, photo store, logs,
  supply chain), abuse cases, OWASP API Top 10 (2023) coverage, residual risks and assumptions.
  Every control is mapped to an existing automated test (all references verified).
- `docs/test-plan.md`: scope and rules of engagement (localhost only, third parties excluded),
  environment, WSTG v4.2 methodology, 40+ test cases traced to the threat model with expected
  secure behaviour and the automated test, CVSS v3.1 scoring, finding template, exit criteria.

### Added — Milestone 12: GeoServer (2026-11-21)
- Opt-in `geoserver` compose profile: GeoServer 2.28.0 (digest-pinned) on 127.0.0.1:8080,
  mandatory admin password, demo data skipped, unprivileged Tomcat, `cap_drop: ALL` plus the minimum
  needed to drop privileges, `no-new-privileges`, CORS off.
- `geoserver_ro` database role (`db/init/30_geoserver_role.sh`, idempotent): SELECT on the
  `public_places` view only (migration `0010`), read-only transactions, statement timeout.
- `geoserver/bootstrap.py` (REST, idempotent): workspace, PostGIS store as `geoserver_ro`, one
  published layer, WFS service level BASIC (no transactions), WCS disabled.
- `geoserver/verify.py`: 16 checks, including default/anonymous credentials refused, only
  `public_places` advertised, private typeNames refused, WFS-T rejected, an admin-published
  `favourites` layer returning no data, and no LAN exposure. All pass.
- `tests/integration/test_geoserver_role.py` (12 tests, CI) and `docs/geoserver.md`.

### Added — Milestone 10: the full interface (2026-11-21)
- New visual world, the "safe-deposit hall": vault-green enamel rail and header, steel map, brass
  reserved for number plates, the primary action and focus, engraved condensed-caps plates,
  self-hosted Archivo (wght+wdth) and JetBrains Mono (OFL), and an authored SVG icon sprite.
- Vanilla-JS ES-module app with a hash router: Hall (search, category plates, nearby, Bhuvan
  link-out), sign-in and registration, My vault (numbered boxes, deposit by map click or from a
  public place), box detail (owner truth, the cloak lens, photo, keys, visibility, delete),
  Keys (shared with me), public share-link view, Account (profile, export, delete), and
  Register (admin users/roles and access register).
- `GET /api/favourites/{id}/cloak-preview` (owner only): the server-computed cell and point
  that recipients get at each precision, drawn by the cloak lens.
- Security: access token in memory only, silent refresh with CSRF header, share tokens in the URL
  fragment, textContent-only rendering, CSP-compatible (no inline code); CSP `img-src` gains
  `blob:` for photos fetched with auth.
- Static tests now cover every frontend module (DOM sinks, storage, import resolution, inline
  styles, font licences); 283 tests in total.
- `PRODUCT.md`, `DESIGN.md` and UI screenshots in `docs/images/`.

### Added — Ahmedabad region (2026-11-20)
- Migration `0009_region_ahmedabad` (UTM 43N cloaking CRS, city-zoom clamp) and an OpenStreetMap
  snapshot of 375 public places. Overpass selectors are shared across Indian cities.
- `GEOVAULT_OVERPASS_URL` lets the fetcher use another public Overpass instance when the default
  is overloaded; the manifest records the URL actually used.

### Added — Milestone 9: HTTP hardening and logging (2026-11-20)
- `SecurityHeaders` middleware: strict CSP, nosniff, X-Frame-Options, Referrer-Policy,
  Permissions-Policy, COOP/CORP, `no-store` on `/api/*`, HSTS in production; route-specific
  headers preserved; relaxed CSP only for local Swagger UI.
- `RequestContext` middleware: validated/generated `X-Request-ID`, redacting JSON access log
  without query strings, and a central generic 500 handler (details only in server logs).
- JSON logging for app and uvicorn with redaction of JWTs, bearer tokens, password/secret
  fields, emails, DSNs, share tokens and coordinates.
- Uvicorn runs with `--no-server-header --no-access-log`. CORS deliberately not enabled.
- 28 new tests (256 total).

### Added — Milestone 8: photos (2026-11-20)
- `POST/GET/DELETE /api/favourites/{id}/photo` (owner) and photo routes for valid share links
  and received shares; `has_photo` on owner and shared views.
- Sanitising pipeline (Pillow 13): content-based format detection (JPEG/PNG/WebP only), pixel
  limit before decode, orientation applied, pixels rebuilt into a fresh image so all metadata
  (EXIF incl. GPS, XMP, ICC, PNG text) is dropped, then re-encoded.
- `UploadGuard` ASGI middleware: 411 without Content-Length, 413 above 5 MB, before multipart
  parsing; received bytes counted.
- Random UUID storage keys with path-containment checks and atomic writes; files removed on
  replace, photo delete, favourite delete and account deletion. Photos volume owned by the
  unprivileged user; `/tmp` tmpfs size-capped.
- Migration `0008`: one photo per favourite. Safe delivery headers (nosniff, sandbox CSP, no-store).
- `docs/privacy/photo-handling.md`; 38 new tests (228 total).

### Added — Milestone 7: favourites and sharing (2026-11-20)
- Favourites CRUD (`/api/favourites`). Server-derived region; create from coordinates or a public
  place; exact location and private note returned only to the owner; per-user cap.
- Object-level authorization via one `get_owned_favourite` dependency: non-owners get the same
  404 as a missing id on every favourite and share route.
- Sharing with registered users (by email) or expiring links (1 h to 30 days). Link tokens are
  256-bit, shown once and stored as SHA-256. Revocation; share creation rate-limited per user.
- `GET /api/shared/{token}` (anonymous, `Referrer-Policy: no-referrer`), `GET /api/shared/with-me`,
  `GET /api/favourites/public`.
- Migration `0007_cloaking`: SQL `cloak_point()` snaps non-owner locations to the centre of a
  100/500/1000 m grid cell in each region's metric CRS (MGA 55 / UTM 43N). Shared views carry
  no note, email or linked place; making a favourite private disables its shares.
- `docs/privacy/location-precision.md`; 59 new tests (190 total).

### Added — Milestone 6: accounts and administration (2026-11-20)
- `PATCH /api/users/me` (display name only), `GET /api/users/me/export` (JSON download),
  `DELETE /api/users/me` (password re-entry, rate-limited; erase content, anonymise identity,
  retain audit evidence; last admin protected).
- `GET /api/admin/users`, `PATCH /api/admin/users/{id}/role`, `GET /api/admin/audit`, all behind a
  router-level `require_admin` that reads the role from the database; no self role change.
- Operator CLI `python -m app.manage promote-admin <email>` to bootstrap the first admin (audited).
- `Cache-Control: no-store` on all account and admin responses.
- 30 new tests (131 total); authorization and data-rights sections in `docs/authentication.md`.

### Added — Milestone 5: authentication (2026-11-20)
- Migrations `0004` (users, refresh_tokens, audit_log), `0005` (favourites, shares, photos with
  defensive constraints), `0006` (checkins_synthetic, synthetic data only).
- `POST /api/auth/register|login|refresh|logout`, `GET /api/users/me`.
- Argon2id hashing; password policy (12-128 chars, 30,492 breached passwords from SecLists (MIT),
  repetition and email checks); per-account and per-IP login rate limiting; registration rate limit.
- HS256 access tokens (15 min, pinned algorithm, required claims, role never in the token) and
  opaque refresh tokens stored as SHA-256, rotated on use, with family revocation on reuse.
- HttpOnly/Secure/SameSite=Strict refresh cookie scoped to `/api/auth`; `__Host-` CSRF cookie
  and `X-CSRF-Token` double-submit for refresh and logout.
- Audit events for every auth action, without secrets or attempted email addresses.
- 422 responses no longer echo submitted input (FastAPI's default would return a rejected password).
- Start-up refuses weak `GEOVAULT_JWT_SECRET` values and token lifetimes above safe caps.
- `docs/authentication.md`: flow, control-to-test mapping, token-storage decision, residual risks.
- 51 new tests (101 total).

### Added — Milestone 3: tests and CI (2026-11-20)
- 50 pytest tests against real PostGIS: API behaviour, input caps (API4), SQL-injection payloads,
  DB privileges/constraints/trigger/migrations, import integrity and pruning, adapter privacy
  exclusions, static frontend XSS/CSP/SRI guards, docs disabled in production.
- `compose.test.yml`: isolated test project (`geovault-test`) with an in-memory database;
  `tests/conftest.py` refuses any non-test database host.
- Dockerfile `test` stage (pytest never ships in the runtime image); `app/requirements-dev.txt`.
- GitHub Actions CI: ruff, tests, Gitleaks (full history), pip-audit, Trivy image + config scans;
  SHA-pinned actions, digest-pinned scanner images, read-only token.
- Pre-commit hooks: ruff, Gitleaks, private-key detection, YAML/JSON checks, file hygiene.

### Security
- Trivy found HIGH CVE-2026-85091 (zlib heap overflow) in the Debian base layer; the image now
  applies Debian security updates at build time (zlib1g 1.3.1-1+deb13u1). Image scan is clean.

### Added — Milestone 2: real open data (2026-11-20)
- Dataset catalogue `data/sources.py`: 5 City of Melbourne datasets (CC BY 4.0) and an
  OpenStreetMap Bengaluru extract (ODbL), each with an adapter into one shared category list.
- `data/fetch_sources.py`: one-time HTTPS snapshot download (stdlib only) with
  `data/raw/MANIFEST.json` recording licence, attribution, URL, fetch time and SHA-256.
- `data/import_sources.py`: offline import that verifies each snapshot hash, records provenance,
  upserts, prunes stale rows, and runs one transaction per source. Re-import is idempotent.
- Migration `0003_place_sources` and `GET /api/sources` for licence attribution.
- Map: viewport-based loading with cap notice, data-source attributions in the sidebar,
  Bhuvan 2D link-out and copy-coordinates for Bengaluru places, stale-response guard.
- `docs/data-sources.md`: provenance, exclusions, known gaps, refresh procedure, manual
  Indian-government data workflow, Bhuvan licence reasoning.

### Changed
- Hand-made sample rows replaced by ~2,900 real places (925 Melbourne, 1,995 Bengaluru).
  `data/samples/` is kept as a small test seed.
- Melbourne landmarks exclude offices, vacant land, industrial sites and private dwellings.
- `.gitattributes`: `data/raw/**` stored byte-exact so snapshot hashes survive Windows checkouts.

### Added — Milestone 1: starter (2026-11-20)
- Docker Compose stack: PostGIS 16-3.5 + FastAPI API (Python 3.12), images pinned by digest.
- Public places API: `/api/health`, `/api/categories`, `/api/places`, `/api/places/near`,
  `/api/places/{id}`, plus `/` (map UI) and `/docs` (local only).
- Numbered SQL migration runner (`app/migrate.py`) with advisory lock; migration `0001_places`
  (GIST indexes on geometry and geography, Victoria bounding-box check, `(source, source_id)` unique key).
- Least-privilege `geovault_app` database role created at DB initialisation.
- Idempotent GeoJSON loader with per-feature validation and rejection report.
- Leaflet map UI: search, category filters, nearby search, place details, responsive layout.
- Hardening: non-root container, read-only root FS, capabilities dropped, 127.0.0.1-only port
  binding, statement timeout, input caps, vendored Leaflet with SRI, `textContent`-only rendering.
- Ruff configuration including bandit (`S`) security rules.
- `GEOVAULT_API_PORT` to change the host port when 8000 is in use.

### Added — Multi-region support: Melbourne (AU) + Bengaluru (IN) (2026-11-20)
- Migration `0002_regions`: `regions` table (bounds, centre, zoom limits, projected CRS for
  cloaking), `places.region` foreign key, and a trigger enforcing that every place lies inside its
  region (replaces the Victoria-only check from `0001`, which is left unmodified).
- `GET /api/regions`; optional `region` filter on `/api/categories`, `/api/places`, `/api/places/near`.
- Loader requires `--region`; samples moved to `data/samples/{melbourne,bengaluru}.geojson`.
- Map UI region switcher; each region's view is clamped to city bounds at city zoom so national
  boundaries are never rendered.
