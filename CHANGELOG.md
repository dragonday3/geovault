# Changelog

All notable changes to GeoVault. Format: [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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
