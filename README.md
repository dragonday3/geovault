# GeoVault

A multi-region geospatial web application built on public open data for **Melbourne, Australia**
and **Bengaluru, India**, developed as a security portfolio project: build it, threat-model it, attack a deliberately vulnerable
**local lab** instance, remediate, and prove the fixes with regression tests.

> **Status: Milestone 1 — starter.** Public places API + map. Authentication, favourites,
> sharing, lab mode, GeoServer and CI arrive in later milestones (see `CHANGELOG.md`).
> Only features listed under *What works now* are implemented.

## What works now

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | API + database health (`503` if the DB is unreachable) |
| `GET /api/regions` | Supported regions with bounds, centre and zoom limits |
| `GET /api/categories` | Place categories with counts; optional `region` |
| `GET /api/places` | Filter by `region`, `category`, name search `q`, `bbox=minLon,minLat,maxLon,maxLat`; `limit` ≤ 500 |
| `GET /api/places/near` | `lat`, `lon`, `radius_m` ≤ 5000, `limit` ≤ 100, optional `region`/`category`; nearest first with `distance_m` |
| `GET /api/places/{id}` | Single place |
| `GET /` | Leaflet map UI: region switcher, search, category filters, click-to-search nearby |
| `GET /docs` | OpenAPI docs (local environment only; disabled when `GEOVAULT_ENV=production`) |

Responses are GeoJSON with explicit response schemas.

## Stack

PostgreSQL 16 + PostGIS 3.5 · FastAPI · Psycopg 3 · Python 3.12 · Leaflet 1.9.4 (vendored) · Docker Compose

## Quick start

Prerequisites: Docker Desktop.

```powershell
# 1. Create your local secrets file (gitignored) and put strong random values in it
Copy-Item .env.example .env
py -3.10 -c "import secrets; print(secrets.token_urlsafe(32))"   # run twice, paste into .env

# 2. Start the stack (first run builds the API image and initialises the database)
docker compose up -d --build
docker compose ps            # api and db should both show (healthy)

# 3. Load the sample places for each region
docker compose run --rm -v ./data:/srv/data:ro api python /srv/data/load_places.py /srv/data/samples/melbourne.geojson --region melbourne --source sample
docker compose run --rm -v ./data:/srv/data:ro api python /srv/data/load_places.py /srv/data/samples/bengaluru.geojson --region bengaluru --source sample
```

macOS/Linux: use `cp .env.example .env` and `python3 -c ...`; the other commands are identical.

Open <http://127.0.0.1:8000> (or the port set in `GEOVAULT_API_PORT`).

```powershell
curl.exe -s http://127.0.0.1:8000/api/health
# {"status":"ok","db":"ok"}
curl.exe -s "http://127.0.0.1:8000/api/places/near?lat=-37.8136&lon=144.9631&radius_m=1000&limit=5"
```

**Troubleshooting**

- `port is already allocated` → another service uses 8000; set `GEOVAULT_API_PORT=8010` in `.env`.
- `set POSTGRES_PASSWORD in .env` → you skipped step 1.
- Changed DB passwords after the first run? The DB is initialised once per volume:
  `docker compose down -v` (**deletes local data**) then start again.

## Security design (implemented so far)

- **Network exposure:** the API is published on `127.0.0.1` only; the database has no published port.
- **Least-privilege database role:** the API connects as `geovault_app` (not superuser, cannot create
  roles, cannot read server files). PostGIS is installed by the superuser at init time.
- **SQL injection:** every query is a static string with bound parameters; optional filters use
  `(%(x)s IS NULL OR col = %(x)s)` instead of string building. Ruff's bandit rules (`S608`) run on all code.
- **Resource limits (OWASP API4):** radius, result-count, offset and input-length caps; a 5 s
  `statement_timeout` on every DB connection.
- **Container hardening:** non-root user (uid 10001), read-only root filesystem, all Linux
  capabilities dropped, `no-new-privileges`, base images pinned by digest, health checks.
- **Frontend:** API data is rendered with `textContent` only (no `innerHTML`); Leaflet is self-hosted
  and pinned with Subresource Integrity hashes.
- **Secrets:** read from environment (`.env`, gitignored); the DB DSN is a `SecretStr` so it never
  appears in logs or reprs.

## Regions and data

| Region | Country | Projected CRS (precision cloaking) | Planned open data (milestone 2) |
|---|---|---|---|
| `melbourne` | AU | EPSG:7855 GDA2020 / MGA 55 | City of Melbourne Open Data (CC BY 4.0) |
| `bengaluru` | IN | EPSG:32643 WGS 84 / UTM 43N | Open Government Data Platform India (GODL-India) and other openly licensed civic data |

`data/samples/*.geojson` are small hand-made seeds of well-known public places (approximate
coordinates), replaced by the open datasets in milestone 2. The loader (`data/load_places.py`)
upserts on `(source, source_id)`, converts polygons to an interior point, and rejects invalid
geometry, missing fields and points outside the region. Region bounds are also enforced in the
database by a trigger, so no writer can bypass them.

**Map boundaries (India).** Each region's map is clamped to its city bounds at a minimum zoom, so
national and international boundaries are never rendered. This avoids depicting India's borders
differently from the official Survey of India depiction. An optional ISRO Bhuvan basemap is planned
for the Bengaluru view, subject to Bhuvan's terms of use.

## Project layout

```
app/            FastAPI application (config, database pool, migrations runner, routers, schemas)
db/init/        one-time database bootstrap (least-privilege app role)
db/migrations/  numbered SQL migrations, applied automatically at API start-up
data/           regional sample data + GeoJSON loader
frontend/       static map UI (vanilla JS + vendored Leaflet)
docs/           plans and (later) security documentation
```

## Scope and ethics

Security testing in this project targets **only** GeoVault instances owned by the developer on
localhost or the developer's own AWS account. No City of Melbourne, Government of India / data.gov.in,
ISRO Bhuvan, OpenStreetMap or other third-party infrastructure is ever scanned or tested.

Map tiles © OpenStreetMap contributors.
