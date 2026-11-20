"""Dataset adapters: privacy exclusions, shared vocabulary, stable ids. No database needed."""

import json
from pathlib import Path

import pytest

from sources import CATEGORIES, SOURCES

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"


def _pt(lon=144.96, lat=-37.81):
    return {"type": "Point", "coordinates": [lon, lat]}


def test_private_dwellings_and_offices_are_excluded():
    adapter = SOURCES["com-landmarks"]["adapter"]
    for sub_theme in ("Dwelling (House)", "Office", "Vacant Land - Undeveloped Site"):
        f = {"properties": {"feature_name": "Somewhere", "sub_theme": sub_theme}, "geometry": _pt()}
        assert adapter(f) is None, sub_theme


def test_landmark_maps_into_shared_vocabulary():
    adapter = SOURCES["com-landmarks"]["adapter"]
    f = {"properties": {"feature_name": "Library X", "sub_theme": "Library"}, "geometry": _pt()}
    _, name, category = adapter(f)
    assert (name, category) == ("Library X", "Library")


def test_hash_ids_are_stable_and_location_sensitive():
    adapter = SOURCES["com-landmarks"]["adapter"]
    f = {"properties": {"feature_name": "A", "sub_theme": "Library"}, "geometry": _pt()}
    g = {"properties": {"feature_name": "A", "sub_theme": "Library"}, "geometry": _pt(lon=144.97)}
    assert adapter(f)[0] == adapter(f)[0]
    assert adapter(f)[0] != adapter(g)[0]


@pytest.mark.parametrize(
    "tags, expected",
    [
        ({"amenity": "charging_station"}, ("EV charging station", "EV charging")),
        ({"amenity": "toilets"}, ("Public toilet", "Public toilet")),
        ({"railway": "station", "station": "subway", "name": "Majestic"}, ("Majestic", "Transport")),
        (
            {"leisure": "park", "name": "ಕಬ್ಬನ್ ಉದ್ಯಾನವನ", "name:en": "Cubbon Park"},
            ("Cubbon Park", "Park and garden"),
        ),
        ({"shop": "bakery", "name": "Not a POI we import"}, None),
    ],
)
def test_osm_adapter(tags, expected):
    result = SOURCES["osm-bengaluru"]["adapter"]({"properties": {**tags, "@id": "node/1"}, "geometry": _pt()})
    assert (result[1:] if result else None) == expected


@pytest.mark.parametrize("key", list(SOURCES))
def test_every_snapshot_feature_maps_to_a_known_category(key):
    features = json.loads((RAW / f"{key}.geojson").read_text(encoding="utf-8"))["features"]
    mapped = [m for m in (SOURCES[key]["adapter"](f) for f in features) if m]
    assert mapped, f"{key} produced no rows"
    assert {m[2] for m in mapped} <= set(CATEGORIES)
    ids = [m[0] for m in mapped]
    assert len(ids) == len(set(ids)), f"{key} has duplicate source ids"


def test_sources_are_https_and_licensed():
    for key, src in SOURCES.items():
        assert src["url"].startswith("https://"), key
        assert src["licence"] and src["attribution"], key
