# Changelog

All notable changes to GeoVault. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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
