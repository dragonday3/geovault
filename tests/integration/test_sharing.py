"""Sharing, location cloaking and excessive-data-exposure controls (OWASP API3).

The LAB-03 lab variant will leak exact coordinates and the owner's email through shared views;
these tests prove secure mode returns only cloaked, minimal data.
"""

import hashlib
import math
import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from tests.helpers import PASSWORD, make_user

EXACT = {"lat": -37.81361, "lon": 144.96312}
SHARED_KEYS = {"label", "region", "location", "owner_display_name", "shared_at", "expires_at"}


def metres(a, b) -> float:
    """Equirectangular distance; accurate to well under 1% at city scale."""
    lat = math.radians((a["lat"] + b["lat"]) / 2)
    dx = math.radians(b["lon"] - a["lon"]) * math.cos(lat) * 6_371_000
    dy = math.radians(b["lat"] - a["lat"]) * 6_371_000
    return math.hypot(dx, dy)


def create(client, user, **overrides):
    body = {
        "label": "Home",
        "note": "secret note",
        "location": EXACT,
        "visibility": "shared",
        "share_precision_m": 500,
    } | overrides
    r = client.post("/api/favourites", json=body, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def share_link(client, user, fav, hours=24):
    r = client.post(
        f"/api/favourites/{fav['id']}/share",
        json={"type": "link", "expires_in_hours": hours},
        headers=user["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def assert_minimal_and_cloaked(view: dict, owner: dict, precision: int):
    assert set(view) == SHARED_KEYS  # nothing else: no note, place, id, email
    text = str(view)
    assert "secret note" not in text and owner["email"] not in text
    loc = view["location"]
    assert loc["precision_m"] == precision
    assert (loc["lat"], loc["lon"]) != (EXACT["lat"], EXACT["lon"])
    # Cell centre is at most half a cell diagonal from the true point.
    assert metres(EXACT, loc) <= precision * math.sqrt(2) / 2 + 1


# --- link shares -----------------------------------------------------------------------------


def test_link_share_shows_only_cloaked_minimal_data(client):
    owner = make_user(client, display_name="Owner Name")
    fav = create(client, owner)
    share = share_link(client, owner, fav)
    assert share["type"] == "link" and share["token"] and share["path"].endswith(share["token"])

    r = client.get(share["path"])  # anonymous: no Authorization header
    assert r.status_code == 200
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    view = r.json()
    assert view["owner_display_name"] == "Owner Name" and view["label"] == "Home"
    assert_minimal_and_cloaked(view, owner, 500)


@pytest.mark.parametrize("precision", [100, 500, 1000])
def test_cloaking_respects_each_precision(client, precision):
    owner = make_user(client)
    fav = create(client, owner, share_precision_m=precision)
    view = client.get(share_link(client, owner, fav)["path"]).json()
    assert_minimal_and_cloaked(view, owner, precision)


def test_cloaking_is_deterministic_and_grid_aligned(client):
    """Repeated views cannot be averaged, and two nearby points in one cell are identical."""
    owner = make_user(client)
    a = create(client, owner, share_precision_m=1000)
    b = create(
        client, owner, share_precision_m=1000, location={"lat": EXACT["lat"] + 0.0001, "lon": EXACT["lon"]}
    )
    path = share_link(client, owner, a)["path"]
    views = {tuple(client.get(path).json()["location"].values()) for _ in range(5)}
    assert len(views) == 1
    loc_b = client.get(share_link(client, owner, b)["path"]).json()["location"]
    assert tuple(loc_b.values()) in views


def test_shared_view_never_reveals_linked_place(client):
    """A favourite created from a public place must not leak that place (its exact position)."""
    owner = make_user(client)
    place = client.get("/api/places", params={"q": "Federation Square"}).json()["features"][0]
    r = client.post(
        "/api/favourites",
        json={
            "label": "Meet here",
            "place_id": place["id"],
            "visibility": "shared",
            "share_precision_m": 500,
        },
        headers=owner["headers"],
    )
    view = client.get(share_link(client, owner, r.json())["path"]).json()
    assert set(view) == SHARED_KEYS
    assert [view["location"]["lon"], view["location"]["lat"]] != place["geometry"]["coordinates"]


def test_link_token_is_shown_once_and_stored_hashed(client, conn):
    owner = make_user(client)
    fav = create(client, owner)
    share = share_link(client, owner, fav)
    listed = client.get(f"/api/favourites/{fav['id']}/shares", headers=owner["headers"]).json()
    assert listed[0]["id"] == share["id"] and listed[0]["token"] is None
    stored = conn.execute("SELECT share_token_hash FROM shares WHERE id = %s", (share["id"],)).fetchone()[0]
    assert bytes(stored) == hashlib.sha256(share["token"].encode()).digest()


def test_revoked_link_is_404(client):
    owner = make_user(client)
    fav = create(client, owner)
    share = share_link(client, owner, fav)
    r = client.delete(f"/api/favourites/{fav['id']}/shares/{share['id']}", headers=owner["headers"])
    assert r.status_code == 204
    assert client.get(share["path"]).status_code == 404


def test_expired_link_is_404(client, dsn):
    owner = make_user(client)
    fav = create(client, owner)
    share = share_link(client, owner, fav)
    with psycopg.connect(dsn) as c:
        c.execute(
            "UPDATE shares SET created_at = now() - interval '2 days', "
            "expires_at = now() - interval '1 second' WHERE id = %s",
            (share["id"],),
        )
    assert client.get(share["path"]).status_code == 404


def test_making_favourite_private_disables_existing_shares(client):
    owner = make_user(client)
    fav = create(client, owner)
    share = share_link(client, owner, fav)
    client.patch(f"/api/favourites/{fav['id']}", json={"visibility": "private"}, headers=owner["headers"])
    assert client.get(share["path"]).status_code == 404


def test_owner_account_deletion_kills_links(client):
    owner = make_user(client)
    share = share_link(client, owner, create(client, owner))
    client.request("DELETE", "/api/users/me", json={"password": PASSWORD}, headers=owner["headers"])
    assert client.get(share["path"]).status_code == 404


@pytest.mark.parametrize("token", ["A" * 43, "short", "../../etc/passwd", "x" * 101])
def test_bogus_tokens(client, token):
    assert client.get(f"/api/shared/{token}").status_code in (404, 422)


# --- user shares -----------------------------------------------------------------------------


def test_share_with_registered_user(client):
    owner, friend = make_user(client, display_name="Owner"), make_user(client, display_name="Friend")
    fav = create(client, owner)
    r = client.post(
        f"/api/favourites/{fav['id']}/share",
        json={"type": "user", "email": friend["email"]},
        headers=owner["headers"],
    )
    assert r.status_code == 201
    share = r.json()
    assert share["type"] == "user" and share["recipient_display_name"] == "Friend" and share["token"] is None
    assert friend["email"] not in r.text  # recipient email not echoed back

    received = client.get("/api/shared/with-me", headers=friend["headers"]).json()
    assert len(received) == 1
    view = received[0]
    assert view.pop("share_id") == share["id"]
    assert_minimal_and_cloaked(view, owner, 500)

    # The recipient still cannot open the favourite itself (owner-only route).
    assert client.get(f"/api/favourites/{fav['id']}", headers=friend["headers"]).status_code == 404


def test_revoked_user_share_disappears(client):
    owner, friend = make_user(client), make_user(client)
    fav = create(client, owner)
    share = client.post(
        f"/api/favourites/{fav['id']}/share",
        json={"type": "user", "email": friend["email"]},
        headers=owner["headers"],
    ).json()
    client.delete(f"/api/favourites/{fav['id']}/shares/{share['id']}", headers=owner["headers"])
    assert client.get("/api/shared/with-me", headers=friend["headers"]).json() == []


@pytest.mark.parametrize(
    "body, status",
    [
        ({"type": "user", "email": "nobody-here@example.com"}, 404),
        ({"type": "link", "expires_in_hours": 0}, 422),
        ({"type": "link", "expires_in_hours": 24 * 31}, 422),  # links max 30 days
        ({"type": "carrier-pigeon"}, 422),
        ({"type": "link", "token": "chosen-by-attacker"}, 422),
    ],
)
def test_share_validation(client, body, status):
    owner = make_user(client)
    fav = create(client, owner)
    assert (
        client.post(f"/api/favourites/{fav['id']}/share", json=body, headers=owner["headers"]).status_code
        == status
    )


def test_cannot_share_with_self_or_twice(client):
    owner, friend = make_user(client), make_user(client)
    fav = create(client, owner)
    url = f"/api/favourites/{fav['id']}/share"
    assert (
        client.post(url, json={"type": "user", "email": owner["email"]}, headers=owner["headers"]).status_code
        == 422
    )
    assert (
        client.post(
            url, json={"type": "user", "email": friend["email"]}, headers=owner["headers"]
        ).status_code
        == 201
    )
    assert (
        client.post(
            url, json={"type": "user", "email": friend["email"]}, headers=owner["headers"]
        ).status_code
        == 409
    )


def test_private_favourite_cannot_be_shared(client):
    owner = make_user(client)
    fav = create(client, owner, visibility="private")
    r = client.post(f"/api/favourites/{fav['id']}/share", json={"type": "link"}, headers=owner["headers"])
    assert r.status_code == 409


def test_share_creation_is_rate_limited(client):
    owner = make_user(client)
    fav = create(client, owner)
    codes = [
        client.post(
            f"/api/favourites/{fav['id']}/share", json={"type": "link"}, headers=owner["headers"]
        ).status_code
        for _ in range(31)
    ]
    assert codes[:30] == [201] * 30 and codes[30] == 429


# --- public favourites -----------------------------------------------------------------------


def test_public_list_shows_only_public_favourites_cloaked(client):
    name = f"Pub Owner {uuid.uuid4().hex[:8]}"
    owner, viewer = make_user(client, display_name=name), make_user(client)
    create(client, owner, label="Public spot", visibility="public", share_precision_m=1000)
    create(client, owner, label="Shared spot", visibility="shared")
    create(client, owner, label="Private spot", visibility="private")

    listed = client.get(
        "/api/favourites/public", params={"region": "melbourne", "limit": 100}, headers=viewer["headers"]
    )
    mine = [p for p in listed.json() if p["owner_display_name"] == name]
    assert [p["label"] for p in mine] == ["Public spot"]
    entry = mine[0]
    assert set(entry) == {"label", "region", "location", "owner_display_name", "created_at"}
    assert metres(EXACT, entry["location"]) <= 1000 * math.sqrt(2) / 2 + 1
    assert owner["email"] not in listed.text and "secret note" not in listed.text


def test_expiry_is_reported(client):
    owner = make_user(client)
    share = share_link(client, owner, create(client, owner), hours=2)
    expires = datetime.fromisoformat(share["expires_at"].replace("Z", "+00:00"))
    assert 7000 < (expires - datetime.now(UTC)).total_seconds() <= 7200
