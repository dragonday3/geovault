# Data sources

GeoVault publishes **public open data only**. Each dataset is downloaded once as a snapshot,
committed under `data/raw/`, and imported from disk. The running app never calls the
publishers' services. Snapshots are verified against SHA-256 hashes in
`data/raw/MANIFEST.json` before import, so a corrupted or tampered file is refused.

## Current sources

| Key | Region | Publisher / dataset | Licence | Imported |
|---|---|---|---|---|
| `com-landmarks` | Melbourne | City of Melbourne — Landmarks and places of interest | CC BY 4.0 | 207 of 242 (35 skipped, see below) |
| `com-public-toilets` | Melbourne | City of Melbourne — Public toilets | CC BY 4.0 | 74 |
| `com-drinking-fountains` | Melbourne | City of Melbourne — Drinking fountains | CC BY 4.0 | 338 |
| `com-playgrounds` | Melbourne | City of Melbourne — Playgrounds (polygons → interior point) | CC BY 4.0 | 45 |
| `com-public-artworks` | Melbourne | City of Melbourne — Public artworks, fountains and monuments | CC BY 4.0 | 261 |
| `osm-bengaluru` | Bengaluru | OpenStreetMap contributors — Overpass extract | ODbL 1.0 | 1,995 of 1,996 |
| `osm-ahmedabad` | Ahmedabad | OpenStreetMap contributors — Overpass extract (fetched via the kumi.systems public Overpass instance while overpass-api.de returned 502) | ODbL 1.0 | 375 of 375 |

Attribution text for each source is stored in the `place_sources` table, served by
`GET /api/sources`, and shown in the map sidebar. CC BY 4.0 and ODbL both require it.

### What is deliberately excluded

- **Melbourne landmarks.** Offices, mixed-use buildings, vacant land, industrial sites, store
  yards and **private dwellings** are skipped. They are not public points of interest, and a
  dwelling is someone's home. See `_COM_SUB_THEMES` in `data/sources.py`.
- **OSM.** Only the tags the category mapping needs are kept (`name`, `amenity`, `leisure`,
  …). Contributor metadata, user names and edit history are not stored. Toilets marked
  `access=private|customers|no` are excluded.

### Known gaps (honest limitations)

- The City of Melbourne portal has **no EV-charging dataset**, so Melbourne has no `EV charging` places.
- The landmarks dataset lists only **one library** (The Melbourne Athenaeum Library). City of
  Melbourne branch libraries are not in these datasets.
- OSM coverage for Ahmedabad is thinner than for Bengaluru (375 vs 1,995 places), and Ahmedabad has no EV-charging points in the extract.
- The OSM snapshots reflect volunteer mapping at fetch time. Coverage and naming vary by suburb.

## Category vocabulary

Every source maps into one shared list (`CATEGORIES` in `data/sources.py`), so a filter means
the same thing in both cities: Park and garden, Playground, Library, Museum and gallery,
Theatre and venue, Public art and monument, Landmark, Sport and recreation, Place of worship,
Education, Health, Emergency services, Transport, Market and shopping, Public toilet,
Drinking water, EV charging.

## Refreshing a snapshot

```powershell
py -3.10 data/fetch_sources.py com-landmarks        # one source (or omit the key for all)
# If the default Overpass server is overloaded (502/504), use another public instance:
$env:GEOVAULT_OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"; py -3.10 data/fetch_sources.py osm-ahmedabad
docker compose run --rm -v ./data:/srv/data:ro api python /srv/data/import_sources.py com-landmarks
```

The fetcher makes one HTTPS download per dataset: City of Melbourne's export API, and a
single Overpass query for OSM. It sends a project User-Agent and waits between requests.
This is ordinary data download, **not** scanning or testing. GeoVault's rules of engagement
forbid any security testing of City of Melbourne, Government of India, OpenCity, ISRO/NRSC
Bhuvan or OpenStreetMap infrastructure.

Re-importing is idempotent. Rows are upserted on `(source, source_id)`, and rows that
disappeared from a snapshot are pruned. Each source imports in a single transaction.

## Adding Indian government datasets (manual download)

OpenCity (data.opencity.in) blocks automated clients with a bot challenge, and data.gov.in's
API needs a registered key. Neither is bypassed. To add an Indian government source:

1. Download the file in a browser (GeoJSON, KML or CSV with latitude/longitude columns).
2. Note the dataset page URL and its **stated licence**, for example GODL-India, CC BY 4.0
   or public domain. Skip datasets marked non-commercial (`-NC`) or with no licence.
3. Save it under `data/raw/manual/` and open an issue or ask for an adapter. Each source
   gets an entry in `data/sources.py` with its own field mapping and licence. A file is
   never imported without a recorded licence.

## ISRO Bhuvan

Bhuvan's terms of use, as far as published material shows, grant a single-user,
non-transferable, view-only licence. Embedding Bhuvan tiles in a third-party public app
would therefore need permission from NRSC. GeoVault does **not** embed Bhuvan. For
Bengaluru places, the detail panel offers a link to Bhuvan 2D and a *Copy coordinates*
button for Bhuvan's find-by-coordinates tool. Bhuvan publishes no documented deep-link
format, so none is guessed.

## Map boundaries (India)

Each region's map is clamped to its city bounds with a minimum zoom of 11. National and
international boundaries are therefore never rendered, which avoids depicting India's
borders differently from the official Survey of India depiction.
