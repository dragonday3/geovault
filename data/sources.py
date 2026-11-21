"""Catalogue of open datasets GeoVault imports, and how each maps onto `places`.

Each source has: where it comes from, its licence/attribution, and an adapter that turns
one GeoJSON feature into (source_id, name, category) or None to skip it. Every region
shares one category vocabulary so filters mean the same thing in Melbourne and Bengaluru.

Fetching (network) lives in fetch_sources.py; loading (database) in import_sources.py.
"""

import hashlib
from collections.abc import Callable

CATEGORIES = (
    "Park and garden",
    "Playground",
    "Library",
    "Museum and gallery",
    "Theatre and venue",
    "Public art and monument",
    "Landmark",
    "Sport and recreation",
    "Place of worship",
    "Education",
    "Health",
    "Emergency services",
    "Rail, metro and tram",
    "Bus and BRT",
    "Market and shopping",
    "Community centre",
    "Public toilet",
    "Drinking water",
    "EV charging",
    "Post office",
)

Adapter = Callable[[dict], tuple[str, str, str] | None]


def _hash_id(*parts: object) -> str:
    """Stable id for datasets that publish none: hash of name + coordinates."""
    # Not a security use: just a deterministic, compact identifier.
    key = "|".join(str(p) for p in parts).encode()
    return hashlib.sha1(key, usedforsecurity=False).hexdigest()[:16]


def _point_key(geom: dict) -> tuple:
    if geom and geom.get("type") == "Point":
        lon, lat = geom["coordinates"][:2]
        return round(lon, 6), round(lat, 6)
    return ()


# --- City of Melbourne ------------------------------------------------------------------

# Landmarks sub_theme -> category. Anything not listed is deliberately skipped: offices,
# mixed-use buildings, vacant land, industrial sites and private dwellings are not
# public points of interest (and dwellings are someone's home).
_COM_SUB_THEMES = {
    "Informal Outdoor Facility (Park/Garden/Reserve)": "Park and garden",
    "Outdoor Recreation Facility (Zoo, Golf Course)": "Sport and recreation",
    "Major Sports & Recreation Facility": "Sport and recreation",
    "Indoor Recreation Facility": "Sport and recreation",
    "Gymnasium/Health Club": "Sport and recreation",
    "Private Sports Club/Facility": "Sport and recreation",
    "Art Gallery/Museum": "Museum and gallery",
    "Library": "Library",
    "Theatre Live": "Theatre and venue",
    "Cinema": "Theatre and venue",
    "Function/Conference/Exhibition Centre": "Theatre and venue",
    "Church": "Place of worship",
    "Synagogue": "Place of worship",
    "Primary Schools": "Education",
    "Secondary Schools": "Education",
    "School - Primary and Secondary Education": "Education",
    "Further Education": "Education",
    "Tertiary (University)": "Education",
    "Public Hospital": "Health",
    "Private Hospital": "Health",
    "Medical Services": "Health",
    "Police Station": "Emergency services",
    "Fire Station": "Emergency services",
    "Railway Station": "Rail, metro and tram",
    "Transport Terminal": "Bus and BRT",
    "Observation Tower/Wheel": "Landmark",
    "Aquarium": "Landmark",
    "Bridge": "Landmark",
    "Visitor Centre": "Landmark",
    "Public Buildings": "Landmark",
    "Government Building": "Landmark",
    "Cemetery": "Landmark",
    "Department Store": "Market and shopping",
}


def _com_landmarks(f: dict) -> tuple[str, str, str] | None:
    p = f["properties"]
    category = _COM_SUB_THEMES.get(p.get("sub_theme"))
    name = p.get("feature_name")
    if not category or not name:
        return None
    return _hash_id(name, *_point_key(f["geometry"])), name, category


def _com_toilets(f: dict) -> tuple[str, str, str] | None:
    name = f["properties"].get("name") or "Public toilet"
    return _hash_id(name, *_point_key(f["geometry"])), name, "Public toilet"


def _com_fountains(f: dict) -> tuple[str, str, str] | None:
    p = f["properties"]
    if not p.get("assetid"):
        return None
    # Published descriptions are asset specs ("Stainless Steel ... Leaf Type"), not names.
    return str(p["assetid"]), "Drinking fountain", "Drinking water"


def _com_playgrounds(f: dict) -> tuple[str, str, str] | None:
    p = f["properties"]
    if not p.get("name"):
        return None
    return str(p.get("council_re") or _hash_id(p["name"])), p["name"], "Playground"


def _com_artworks(f: dict) -> tuple[str, str, str] | None:
    p = f["properties"]
    name = p.get("name")
    if not name:
        return None
    return _hash_id(name, *_point_key(f["geometry"])), name, "Public art and monument"


def _com(dataset_id: str) -> str:
    return f"https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/{dataset_id}/exports/geojson"


_COM = {
    "region": "melbourne",
    "kind": "geojson",
    "publisher": "City of Melbourne",
    "licence": "CC BY 4.0",
    "attribution": "Contains data © City of Melbourne, licensed under CC BY 4.0",
}

# --- OpenStreetMap: Bengaluru ---------------------------------------------------------------

# One polite Overpass query per city, run once to produce a committed snapshot
# (fetch_sources.py). Point-of-interest selectors are shared by every Indian city.
_OSM_POI_SELECTORS = """
(
  // transport: every rail/metro/tram stop, every bus stop and BRT station (AMTS, BMTC, Janmarg...)
  nwr["railway"~"^(station|halt|tram_stop)$"];
  nwr["public_transport"="station"];
  nwr["highway"="bus_stop"];
  nwr["amenity"="bus_station"];
  // health and emergency
  nwr["amenity"~"^(hospital|clinic|police|fire_station)$"];
  // education
  nwr["amenity"~"^(school|college|university)$"]["name"];
  // worship and community
  nwr["amenity"~"^(place_of_worship|community_centre|marketplace)$"]["name"];
  // culture and landmarks
  nwr["amenity"="library"];
  nwr["tourism"~"^(museum|gallery)$"];
  nwr["amenity"~"^(theatre|arts_centre|cinema)$"]["name"];
  nwr["historic"~"^(monument|memorial|fort|castle)$"]["name"];
  nwr["tourism"="attraction"]["name"];
  // parks, play and sport
  nwr["leisure"="park"]["name"];
  nwr["leisure"="garden"]["name"]["access"!="private"];
  nwr["leisure"="playground"]["name"];
  nwr["leisure"~"^(sports_centre|stadium)$"]["name"];
  // everyday amenities
  nwr["amenity"="toilets"]["access"!~"^(private|customers|no)$"];
  nwr["amenity"="drinking_water"];
  nwr["amenity"="charging_station"];
  nwr["amenity"="post_office"];
);
out center tags;
"""


def _osm_query(south: float, west: float, north: float, east: float) -> str:
    """One Overpass query per city; the bbox matches that city's regions.bounds."""
    return (
        f"[out:json][timeout:600][maxsize:536870912][bbox:{south},{west},{north},{east}];"
        + _OSM_POI_SELECTORS
    )


OSM_BENGALURU_QUERY = _osm_query(12.75, 77.35, 13.20, 77.90)
OSM_AHMEDABAD_QUERY = _osm_query(22.90, 72.40, 23.20, 72.75)
OSM_MELBOURNE_QUERY = _osm_query(-37.95, 144.80, -37.70, 145.10)


_RAIL_MODES = ("train", "subway", "light_rail", "tram", "monorail")

_SIMPLE_AMENITIES = {
    "charging_station": "EV charging",
    "toilets": "Public toilet",
    "drinking_water": "Drinking water",
    "post_office": "Post office",
    "hospital": "Health",
    "clinic": "Health",
    "police": "Emergency services",
    "fire_station": "Emergency services",
    "school": "Education",
    "college": "Education",
    "university": "Education",
    "place_of_worship": "Place of worship",
    "community_centre": "Community centre",
    "marketplace": "Market and shopping",
    "library": "Library",
    "theatre": "Theatre and venue",
    "arts_centre": "Theatre and venue",
    "cinema": "Theatre and venue",
}


def _osm_category(t: dict) -> str | None:
    amenity, leisure = t.get("amenity"), t.get("leisure")
    station = t.get("public_transport") == "station"
    # Transport first: a station can also carry amenity/leisure tags.
    if t.get("railway") in ("station", "halt", "tram_stop") or (
        station and any(t.get(m) == "yes" for m in _RAIL_MODES)
    ):
        return "Rail, metro and tram"
    if t.get("highway") == "bus_stop" or amenity == "bus_station" or station:
        # Untagged-mode stations here are overwhelmingly bus/BRT (e.g. Janmarg in Ahmedabad).
        return "Bus and BRT"
    if amenity in _SIMPLE_AMENITIES:
        return _SIMPLE_AMENITIES[amenity]
    if t.get("tourism") in ("museum", "gallery"):
        return "Museum and gallery"
    if leisure == "playground":
        return "Playground"
    if leisure in ("park", "garden"):
        return "Park and garden"
    if leisure in ("sports_centre", "stadium"):
        return "Sport and recreation"
    if t.get("historic"):
        return "Public art and monument"
    if t.get("tourism") == "attraction":
        return "Landmark"
    return None


_OSM_FALLBACK_NAMES = {
    "EV charging": "EV charging station",
    "Public toilet": "Public toilet",
    "Drinking water": "Drinking water",
    "Library": "Library",
    "Bus and BRT": "Bus stop",
    "Rail, metro and tram": "Station",
    "Health": "Clinic",
    "Emergency services": "Emergency service",
    "Post office": "Post office",
}


def _osm(f: dict) -> tuple[str, str, str] | None:
    t = f["properties"]
    category = _osm_category(t)
    if not category:
        return None
    name = t.get("name:en") or t.get("name")
    if not name and category in _OSM_FALLBACK_NAMES:
        name = _OSM_FALLBACK_NAMES[category] + (f" {t['ref']}" if t.get("ref") else "")
    if not name:
        return None
    return t["@id"], name, category


def _osm_source(region: str, city: str, query: str, **extra) -> dict:
    return {
        "region": region,
        "kind": "overpass",
        "url": "https://overpass-api.de/api/interpreter",
        "query": query,
        "publisher": "OpenStreetMap contributors",
        "dataset": f"{city} public points of interest and transport stops (Overpass extract)",
        "licence": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors, available under the Open Database Licence (ODbL)",
        "adapter": _osm,
        **extra,
    }


SOURCES: dict[str, dict] = {
    "com-landmarks": {
        **_COM,
        "url": _com("landmarks-and-places-of-interest-including-schools-theatres-health-services-spor"),
        "dataset": "Landmarks and places of interest",
        "adapter": _com_landmarks,
    },
    "com-public-toilets": {
        **_COM,
        "url": _com("public-toilets"),
        "dataset": "Public toilets",
        "adapter": _com_toilets,
    },
    "com-drinking-fountains": {
        **_COM,
        "url": _com("drinking-fountains"),
        "dataset": "Drinking fountains",
        "adapter": _com_fountains,
    },
    "com-playgrounds": {
        **_COM,
        "url": _com("playgrounds"),
        "dataset": "Playgrounds",
        "adapter": _com_playgrounds,
    },
    "com-public-artworks": {
        **_COM,
        "url": _com("public-artworks-fountains-and-monuments"),
        "dataset": "Public artworks, fountains and monuments",
        "adapter": _com_artworks,
    },
    "osm-bengaluru": _osm_source("bengaluru", "Bengaluru", OSM_BENGALURU_QUERY),
    "osm-ahmedabad": _osm_source("ahmedabad", "Ahmedabad", OSM_AHMEDABAD_QUERY),
    # Melbourne already has City of Melbourne data inside its LGA; OSM adds transport, libraries
    # and everything outside the LGA. Points within 40 m of an existing same-category place from
    # another source are skipped, so the two sources do not double up.
    "osm-melbourne": _osm_source("melbourne", "Melbourne", OSM_MELBOURNE_QUERY, dedupe_radius_m=40),
}
