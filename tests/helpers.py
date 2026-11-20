"""Shared test helpers: create users through the real API, promote via the operator CLI."""

import uuid

PASSWORD = "correct horse battery staple 42"


def new_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_user(client, dsn=None, *, admin=False, display_name="Test User"):
    """Register + log in a fresh user. Returns dict(email, token, id, headers)."""
    from app.manage import promote_admin

    email = new_email()
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": display_name},
    )
    assert r.status_code == 202, r.text
    if admin:
        assert promote_admin(dsn, email)
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/api/users/me", headers=bearer(token)).json()
    return {"email": email, "token": token, "id": me["id"], "headers": bearer(token)}


def add_favourite(conn, owner_id, label="Home", note="private note", lon=144.9631, lat=-37.8136):
    """Insert a favourite directly (the favourites API arrives in milestone 7)."""
    row = conn.execute(
        """
        INSERT INTO favourites (owner_id, region, label, note, geom)
        VALUES (%s, 'melbourne', %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        RETURNING id
        """,
        (owner_id, label, note, lon, lat),
    ).fetchone()
    conn.commit()
    return row[0]
