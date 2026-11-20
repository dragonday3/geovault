"""Favourites CRUD and object-level authorization (OWASP API1 / BOLA).

The LAB-01 lab variant will remove the ownership check; these secure-mode regression tests
prove that another user can neither read, modify, delete nor share someone's favourite.
"""

import uuid

import pytest

from tests.helpers import make_user

MELB = {"lat": -37.8136, "lon": 144.9631}
BLR = {"lat": 12.9716, "lon": 77.5946}
SYDNEY = {"lat": -33.8688, "lon": 151.2093}


def create(client, user, **overrides):
    body = {"label": "Home", "note": "gate code 4471", "location": MELB} | overrides
    r = client.post("/api/favourites", json=body, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


# --- owner CRUD ------------------------------------------------------------------------------


def test_create_returns_exact_location_and_note_to_owner(client):
    u = make_user(client)
    fav = create(client, u)
    assert fav["location"] == MELB and fav["note"] == "gate code 4471"
    assert fav["region"] == "melbourne" and fav["visibility"] == "private"
    assert fav["share_precision_m"] == 100


def test_region_is_derived_server_side(client):
    u = make_user(client)
    assert create(client, u, location=BLR)["region"] == "bengaluru"
    r = client.post("/api/favourites", json={"label": "Opera", "location": SYDNEY}, headers=u["headers"])
    assert r.status_code == 422 and "outside the supported regions" in r.text


def test_create_from_public_place(client):
    u = make_user(client)
    place = client.get("/api/places", params={"q": "Cubbon Park", "region": "bengaluru"}).json()["features"][
        0
    ]
    fav = create(client, u, location=None, place_id=place["id"], label="Park")
    assert fav["place_id"] == place["id"] and fav["region"] == "bengaluru"
    assert [fav["location"]["lon"], fav["location"]["lat"]] == place["geometry"]["coordinates"]


@pytest.mark.parametrize(
    "body",
    [
        {"label": "x"},  # neither location nor place
        {"label": "x", "location": MELB, "place_id": 1},  # both
        {"label": "x", "location": MELB, "owner_id": str(uuid.uuid4())},  # mass assignment
        {"label": "x", "location": MELB, "region": "bengaluru"},  # region is server-derived
        {"label": "   ", "location": MELB},
        {"label": "x", "location": MELB, "note": "bell\x07"},
        {"label": "x", "location": MELB, "note": "n" * 2001},
        {"label": "x", "location": MELB, "share_precision_m": 10},
        {"label": "x", "location": {"lat": 91, "lon": 0}},
    ],
)
def test_create_validation(client, body):
    u = make_user(client)
    assert client.post("/api/favourites", json=body, headers=u["headers"]).status_code == 422


def test_update_fields_and_move_between_regions(client):
    u = make_user(client)
    fav = create(client, u)
    r = client.patch(
        f"/api/favourites/{fav['id']}",
        json={
            "label": "Work",
            "note": None,
            "visibility": "shared",
            "share_precision_m": 500,
            "location": BLR,
        },
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["label"], out["note"], out["visibility"], out["share_precision_m"]) == (
        "Work",
        None,
        "shared",
        500,
    )
    assert out["location"] == BLR and out["region"] == "bengaluru"
    assert out["updated_at"] > fav["updated_at"]


@pytest.mark.parametrize(
    "body",
    [{}, {"owner_id": str(uuid.uuid4())}, {"label": None}, {"location": SYDNEY}, {"visibility": "everyone"}],
)
def test_update_validation(client, body):
    u = make_user(client)
    fav = create(client, u)
    r = client.patch(f"/api/favourites/{fav['id']}", json=body, headers=u["headers"])
    assert r.status_code == 422


def test_list_contains_only_own_favourites(client):
    alice, bob = make_user(client), make_user(client)
    a = create(client, alice, label="Alice place")
    create(client, bob, label="Bob place")
    labels = [f["label"] for f in client.get("/api/favourites", headers=alice["headers"]).json()]
    assert labels == ["Alice place"]
    assert a["id"] not in client.get("/api/favourites", headers=bob["headers"]).text


def test_delete(client):
    u = make_user(client)
    fav = create(client, u)
    assert client.delete(f"/api/favourites/{fav['id']}", headers=u["headers"]).status_code == 204
    assert client.get(f"/api/favourites/{fav['id']}", headers=u["headers"]).status_code == 404


def test_favourites_require_authentication(client):
    assert client.get("/api/favourites").status_code == 401
    assert client.post("/api/favourites", json={"label": "x", "location": MELB}).status_code == 401
    assert client.get("/api/favourites/public").status_code == 401


def test_per_user_favourite_cap(client, monkeypatch):
    from app.services import favourites as favs

    monkeypatch.setattr(favs, "MAX_FAVOURITES_PER_USER", 2)
    u = make_user(client)
    create(client, u)
    create(client, u)
    r = client.post("/api/favourites", json={"label": "x", "location": MELB}, headers=u["headers"])
    assert r.status_code == 409


def test_audit_records_ids_not_content(client, conn):
    u = make_user(client)
    fav = create(client, u, note="unique-private-note-8812")
    rows = conn.execute("SELECT * FROM audit_log WHERE target_id = %s", (fav["id"],)).fetchall()
    assert rows
    dump = " ".join(str(v) for row in rows for v in row)
    assert "unique-private-note-8812" not in dump and "144.96" not in dump and "-37.81" not in dump


# --- BOLA: another user attacks Alice's favourite ---------------------------------------------


@pytest.fixture
def victim_and_attacker(client):
    alice, mallory = make_user(client), make_user(client)
    fav = create(client, alice, visibility="shared")
    return alice, mallory, fav


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("GET", "/api/favourites/{id}", None),
        ("PATCH", "/api/favourites/{id}", {"label": "pwned"}),
        ("PATCH", "/api/favourites/{id}", {"visibility": "public"}),
        ("DELETE", "/api/favourites/{id}", None),
        ("GET", "/api/favourites/{id}/shares", None),
        ("POST", "/api/favourites/{id}/share", {"type": "link", "expires_in_hours": 1}),
        ("DELETE", "/api/favourites/{id}/shares/" + str(uuid.uuid4()), None),
    ],
)
def test_bola_other_users_favourite_is_404(client, victim_and_attacker, method, path, body):
    alice, mallory, fav = victim_and_attacker
    r = client.request(method, path.format(id=fav["id"]), json=body, headers=mallory["headers"])
    assert r.status_code == 404  # identical to a non-existent id: no existence oracle

    after = client.get(f"/api/favourites/{fav['id']}", headers=alice["headers"])
    assert after.status_code == 200
    assert after.json() == fav  # nothing changed
    assert client.get(f"/api/favourites/{fav['id']}/shares", headers=alice["headers"]).json() == []


def test_bola_nonexistent_and_foreign_ids_are_indistinguishable(client, victim_and_attacker):
    _, mallory, fav = victim_and_attacker
    foreign = client.get(f"/api/favourites/{fav['id']}", headers=mallory["headers"])
    missing = client.get(f"/api/favourites/{uuid.uuid4()}", headers=mallory["headers"])
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_bola_cannot_revoke_foreign_share_via_own_favourite(client, victim_and_attacker):
    alice, mallory, fav = victim_and_attacker
    share = client.post(
        f"/api/favourites/{fav['id']}/share", json={"type": "link"}, headers=alice["headers"]
    ).json()
    own = create(client, mallory)
    r = client.delete(f"/api/favourites/{own['id']}/shares/{share['id']}", headers=mallory["headers"])
    assert r.status_code == 404
    assert client.get(share["path"]).status_code == 200  # Alice's link still works
