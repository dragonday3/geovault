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
| `osm-melbourne` | Melbourne | OpenStreetMap contributors — Overpass extract (greater-Melbourne bbox) | ODbL 1.0 | 13,288 of 13,801 (478 skipped as duplicates of a City of Melbourne place within 40 m, 30 outside the region) |
| `osm-bengaluru` | Bengaluru | OpenStreetMap contributors — Overpass extract | ODbL 1.0 | 13,298 of 13,300 |
| `osm-ahmedabad` | Ahmedabad | OpenStreetMap contributors — Overpass extract | ODbL 1.0 | 1,891 of 1,892 |

Total: **29,402 places** (Melbourne 14,213, Bengaluru 13,298, Ahmedabad 1,891).

### What the OSM extract covers

One Overpass query per city (`_OSM_POI_SELECTORS` in `data/sources.py`):

- **Transport:** every railway station, halt and tram stop; every `highway=bus_stop`,
  `amenity=bus_station` and `public_transport=station` (this is where BRTS/Janmarg and BMTC
  stations appear). Stops with no name are kept as "Bus stop <ref>".
- **Health and emergency:** hospitals, clinics, police and fire stations.
- **Education:** named schools, colleges and universities.
- **Worship, community and markets:** named places of worship, community centres and marketplaces.
- **Culture:** libraries, museums, galleries, theatres, arts centres, cinemas, monuments, memorials, forts, attractions.
- **Parks, play and sport:** named parks, public gardens, playgrounds, sports centres and stadiums.
- **Amenities:** public toilets, drinking water, EV charging, post offices.

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
- **Ahmedabad bus stops are under-mapped.** OSM has about 185 bus/BRT stops for Ahmedabad, while
  AMTS runs roughly 4,000 stops. No open, licensed AMTS stop dataset or GTFS feed was found (the
  TUMI data hub lists only terminals and depots; journey-planner apps are commercial and their data
  is not reusable). The fix is upstream: map the stops in OpenStreetMap, or drop an official file
  into `data/raw/manual/` with its licence and add an adapter. Ahmedabad also has no EV-charging
  points in the extract.
- The OSM snapshots reflect volunteer mapping at fetch time. Coverage and naming vary by suburb.

## Category vocabulary

Every source maps into one shared list (`CATEGORIES` in `data/sources.py`), so a filter means
the same thing in all three cities: Park and garden, Playground, Library, Museum and gallery,
Theatre and venue, Public art and monument, Landmark, Sport and recreation, Place of worship,
Education, Health, Emergency services, Rail metro and tram, Bus and BRT, Market and shopping,
Community centre, Post office, Public toilet,
Drinking water, EV charging.

On the map the categories fold into **eight groups**, each with its own colour *and* shape
(`frontend/js/categories.js`): rail, metro and tram (blue square); bus and BRT (orange diamond);
parks, play and sport (green circle); culture and landmarks (pink circle); health and emergency
(red triangle); education (violet circle); worship, community and markets (yellow square);
everyday amenities (aqua circle). The hues are a colour-blind-validated categorical palette; pairs
that are too close in hue always differ in shape. The chips above the list are the key and the filter.

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
places in the Indian cities (Bengaluru, Ahmedabad), the detail panel offers a link to Bhuvan 2D and a *Copy coordinates*
button for Bhuvan's find-by-coordinates tool. Bhuvan publishes no documented deep-link
format, so none is guessed.

## Map boundaries (India)

Each region's map is clamped to its city bounds with a minimum zoom of 11. National and
international boundaries are therefore never rendered, which avoids depicting India's
borders differently from the official Survey of India depiction.
