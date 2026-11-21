"""Public places API: behaviour, input validation and resource caps (OWASP API4)."""

import pytest

FED_SQUARE = {"lat": -37.8180, "lon": 144.9690}
CUBBON_PARK = {"lat": 12.9763, "lon": 77.5929}


def names(resp) -> list[str]:
    return [f["properties"]["name"] for f in resp.json()["features"]]


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_regions_lists_both_cities(client):
    regions = {r["code"]: r for r in client.get("/api/regions").json()}
    assert set(regions) >= {"melbourne", "bengaluru"}
    assert regions["bengaluru"]["country_code"] == "IN"
    assert regions["melbourne"]["country_code"] == "AU"
    # City-zoom clamp is what keeps national borders off the India map.
    assert all(r["min_zoom"] >= 11 for r in regions.values())


def test_region_filter_isolates_places(client):
    blr = client.get("/api/places", params={"region": "bengaluru", "limit": 500}).json()["features"]
    assert blr and all(f["properties"]["region"] == "bengaluru" for f in blr)
    assert "Cubbon Park" in [f["properties"]["name"] for f in blr]
    assert "Federation Square" not in [f["properties"]["name"] for f in blr]


def test_categories_by_region(client):
    cats = {c["category"]: c["count"] for c in client.get("/api/categories?region=melbourne").json()}
    assert cats.get("Park and garden", 0) >= 6


def test_repeated_category_filters_by_several(client):
    """The map key filters by a group of categories: ?category=A&category=B."""
    cats = sorted(c["category"] for c in client.get("/api/categories?region=melbourne").json())[:2]
    assert len(cats) == 2
    params = [("region", "melbourne"), ("limit", "500")] + [("category", c) for c in cats]
    got = {f["properties"]["category"] for f in client.get("/api/places", params=params).json()["features"]}
    assert got == set(cats)
    near = client.get(
        "/api/places/near",
        params=[
            *params[:1],
            ("lat", FED_SQUARE["lat"]),
            ("lon", FED_SQUARE["lon"]),
            ("radius_m", 5000),
            ("limit", 100),
            *params[2:],
        ],
    )
    assert near.status_code == 200
    assert {f["properties"]["category"] for f in near.json()["features"]} <= set(cats)


def test_category_filter_list_is_capped(client):
    r = client.get("/api/places", params=[("category", f"c{i}") for i in range(21)])
    assert r.status_code == 422


def test_name_search_and_bbox(client):
    r = client.get("/api/places", params={"q": "gardens", "region": "melbourne"})
    assert "Fitzroy Gardens" in names(r)
    r = client.get("/api/places", params={"bbox": "144.96,-37.82,144.97,-37.81"})
    assert {"Federation Square", "Flinders Street Station"} <= set(names(r))


def test_near_is_sorted_by_distance(client):
    r = client.get("/api/places/near", params={**CUBBON_PARK, "radius_m": 1500, "region": "bengaluru"})
    feats = r.json()["features"]
    assert feats[0]["properties"]["name"] == "Cubbon Park"
    dists = [f["properties"]["distance_m"] for f in feats]
    assert dists == sorted(dists) and dists[-1] <= 1500


def test_get_place_and_404(client):
    first = client.get("/api/places", params={"limit": 1}).json()["features"][0]
    r = client.get(f"/api/places/{first['id']}")
    assert r.status_code == 200 and r.json()["id"] == first["id"]
    assert client.get("/api/places/999999999").status_code == 404


@pytest.mark.parametrize(
    "path, params",
    [
        ("/api/places/near", {**FED_SQUARE, "radius_m": 5001}),  # radius cap
        ("/api/places/near", {**FED_SQUARE, "limit": 101}),  # near result cap
        ("/api/places", {"limit": 501}),  # list result cap
        ("/api/places", {"offset": 10_001}),  # deep pagination cap
        ("/api/places", {"q": "x" * 101}),  # input length cap
        ("/api/places", {"bbox": "1,2,3"}),  # malformed bbox
        ("/api/places", {"bbox": "145,-37,144,-38"}),  # inverted bbox
        ("/api/places/near", {"lat": 91, "lon": 0}),  # out-of-range coordinate
        ("/api/places", {"region": "Melbourne'--"}),  # region must match its pattern
    ],
)
def test_input_validation_rejects(client, path, params):
    assert client.get(path, params=params).status_code == 422


def test_like_wildcards_are_literal(client):
    # '%' and '_' are escaped, so they cannot be used to match everything.
    assert names(client.get("/api/places", params={"q": "%"})) == []
    assert names(client.get("/api/places", params={"q": "_"})) == []


@pytest.mark.parametrize(
    "payload",
    [
        "x' OR '1'='1",
        "x'; DROP TABLE places;--",
        "x' UNION SELECT id, name, category, region, source, 0, 0 FROM places--",
    ],
)
def test_sql_injection_payloads_are_inert(client, payload):
    for params in ({"category": payload}, {"q": payload}):
        r = client.get("/api/places", params=params)
        assert r.status_code == 200, r.text  # no 500: payload never reached SQL as code
        assert r.json()["features"] == []
    assert client.get("/api/health").json()["db"] == "ok"  # and nothing was dropped
    assert client.get("/api/places", params={"limit": 1}).json()["features"]


def test_docs_disabled_in_production(dsn):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(database_url=dsn, env="production"))
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
        assert c.get("/api/health").status_code == 200
