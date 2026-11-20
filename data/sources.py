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
    "Transport",
    "Market and shopping",
    "Public toilet",
    "Drinking water",
    "EV charging",
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
    "Railway Station": "Transport",
    "Transport Terminal": "Transport",
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
  nwr["leisure"="park"]["name"];
  nwr["leisure"="garden"]["name"]["access"!="private"];
  nwr["leisure"="playground"]["name"];
  nwr["amenity"="library"];
  nwr["tourism"~"^(museum|gallery)$"];
  nwr["amenity"~"^(theatre|arts_centre)$"]["name"];
  nwr["historic"~"^(monument|memorial|fort|castle)$"]["name"];
  nwr["tourism"="attraction"]["name"];
  nwr["amenity"="toilets"]["access"!~"^(private|customers|no)$"];
  nwr["amenity"="drinking_water"];
  nwr["amenity"="charging_station"];
  nwr["railway"="station"]["station"="subway"];
  nwr["railway"="station"]["operator"~"BMRCL|Bangalore Metro|Namma Metro",i];
  nwr["amenity"="marketplace"]["name"];
);
out center tags;
"""


def _osm_query(south: float, west: float, north: float, east: float) -> str:
    """One Overpass query per city; the bbox matches that city's regions.bounds."""
    return f"[out:json][timeout:180][bbox:{south},{west},{north},{east}];" + _OSM_POI_SELECTORS


OSM_BENGALURU_QUERY = _osm_query(12.75, 77.35, 13.20, 77.90)
OSM_AHMEDABAD_QUERY = _osm_query(22.90, 72.40, 23.20, 72.75)


def _osm_category(t: dict) -> str | None:
    if t.get("amenity") == "charging_station":
        return "EV charging"
    if t.get("amenity") == "toilets":
        return "Public toilet"
    if t.get("amenity") == "drinking_water":
        return "Drinking water"
    if t.get("railway") == "station":
        return "Transport"
    if t.get("amenity") == "library":
        return "Library"
    if t.get("tourism") in ("museum", "gallery"):
        return "Museum and gallery"
    if t.get("amenity") in ("theatre", "arts_centre"):
        return "Theatre and venue"
    if t.get("amenity") == "marketplace":
        return "Market and shopping"
    if t.get("leisure") == "playground":
        return "Playground"
    if t.get("leisure") in ("park", "garden"):
        return "Park and garden"
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
}


def _osm(f: dict) -> tuple[str, str, str] | None:
    t = f["properties"]
    category = _osm_category(t)
    if not category:
        return None
    name = t.get("name:en") or t.get("name") or _OSM_FALLBACK_NAMES.get(category)
    if not name:
        return None
    return t["@id"], name, category


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
    "osm-bengaluru": {
        "region": "bengaluru",
        "kind": "overpass",
        "url": "https://overpass-api.de/api/interpreter",
        "query": OSM_BENGALURU_QUERY,
        "publisher": "OpenStreetMap contributors",
        "dataset": "Bengaluru public points of interest (Overpass extract)",
        "licence": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors, available under the Open Database Licence (ODbL)",
        "adapter": _osm,
    },
    "osm-ahmedabad": {
        "region": "ahmedabad",
        "kind": "overpass",
        "url": "https://overpass-api.de/api/interpreter",
        "query": OSM_AHMEDABAD_QUERY,
        "publisher": "OpenStreetMap contributors",
        "dataset": "Ahmedabad public points of interest (Overpass extract)",
        "licence": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors, available under the Open Database Licence (ODbL)",
        "adapter": _osm,
    },
}
