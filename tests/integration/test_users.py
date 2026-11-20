"""Self-service account endpoints: profile edit (property-level authz), export, deletion."""

import json

import pytest

from tests.helpers import PASSWORD, add_favourite, make_user

# --- PATCH /api/users/me (OWASP API3: property-level authorization) -------------------------


def test_update_display_name(client):
    u = make_user(client)
    r = client.patch("/api/users/me", json={"display_name": "  New   Name "}, headers=u["headers"])
    assert r.status_code == 200 and r.json()["display_name"] == "New Name"
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "body",
    [
        {"display_name": "X", "role": "admin"},  # mass-assignment privilege escalation
        {"role": "admin"},
        {"display_name": "X", "email": "takeover@example.com"},
        {"display_name": "X", "id": "00000000-0000-0000-0000-000000000000"},
        {"display_name": "   "},
    ],
)
def test_update_rejects_protected_or_invalid_fields(client, body):
    u = make_user(client)
    r = client.patch("/api/users/me", json=body, headers=u["headers"])
    assert r.status_code == 422
    me = client.get("/api/users/me", headers=u["headers"]).json()
    assert me["role"] == "user" and me["email"] == u["email"]


def test_account_endpoints_require_authentication(client):
    assert client.get("/api/users/me/export").status_code == 401
    assert client.patch("/api/users/me", json={"display_name": "x"}).status_code == 401
    assert client.request("DELETE", "/api/users/me", json={"password": PASSWORD}).status_code == 401


# --- GET /api/users/me/export -----------------------------------------------------------------


def test_export_contains_own_data_only_and_no_secrets(client, conn):
    alice, bob = make_user(client), make_user(client, display_name="Bob")
    add_favourite(conn, alice["id"], label="Alice home", note="alice secret note", lon=144.95, lat=-37.80)
    add_favourite(conn, bob["id"], label="Bob home", note="bob secret note")

    r = client.get("/api/users/me/export", headers=alice["headers"])
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["cache-control"] == "no-store"

    data = r.json()
    assert data["format"] == "geovault-export/1"
    assert data["profile"]["email"] == alice["email"]
    fav = data["favourites"][0]
    assert (fav["label"], fav["note"], fav["lat"], fav["lon"]) == (
        "Alice home",
        "alice secret note",
        -37.80,
        144.95,
    )
    assert any(a["action"] == "auth.login_success" for a in data["activity"])

    text = json.dumps(data)
    assert "bob secret note" not in text and bob["email"] not in text  # nobody else's data
    assert "argon2" not in text and "token_hash" not in text and "password" not in text


# --- DELETE /api/users/me ---------------------------------------------------------------------


def test_delete_requires_correct_password(client):
    u = make_user(client)
    r = client.request(
        "DELETE", "/api/users/me", json={"password": "not my password at all"}, headers=u["headers"]
    )
    assert r.status_code == 403
    assert client.get("/api/users/me", headers=u["headers"]).status_code == 200


def test_delete_erases_personal_data_and_keeps_anonymised_audit(client, conn):
    u = make_user(client, display_name="Soon Gone")
    fav = add_favourite(conn, u["id"], note="delete me")

    r = client.request("DELETE", "/api/users/me", json={"password": PASSWORD}, headers=u["headers"])
    assert r.status_code == 204
    assert any("gv_refresh=" in c and "max-age=0" in c.lower() for c in r.headers.get_list("set-cookie"))

    # Access token and credentials are dead immediately.
    assert client.get("/api/users/me", headers=u["headers"]).status_code == 401
    assert client.post("/api/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code == 401

    # Personal data gone; row anonymised; sessions removed.
    row = conn.execute(
        "SELECT email, display_name, password_hash, deleted_at FROM users WHERE id = %s", (u["id"],)
    ).fetchone()
    assert row[0] == f"deleted-{u['id']}@invalid" and row[1] == "Deleted user" and row[2] == "!deleted"
    assert row[3] is not None
    assert conn.execute("SELECT count(*) FROM favourites WHERE id = %s", (fav,)).fetchone()[0] == 0
    assert (
        conn.execute("SELECT count(*) FROM refresh_tokens WHERE user_id = %s", (u["id"],)).fetchone()[0] == 0
    )
    assert conn.execute("SELECT count(*) FROM users WHERE email = %s", (u["email"],)).fetchone()[0] == 0

    # Security evidence retained (and still attributable to the anonymised id).
    actions = {r[0] for r in conn.execute("SELECT action FROM audit_log WHERE actor_id = %s", (u["id"],))}
    assert {"auth.register", "auth.login_success", "user.delete"} <= actions


def test_deleted_email_can_register_again(client):
    u = make_user(client)
    client.request("DELETE", "/api/users/me", json={"password": PASSWORD}, headers=u["headers"])
    r = client.post(
        "/api/auth/register", json={"email": u["email"], "password": PASSWORD, "display_name": "Again"}
    )
    assert r.status_code == 202
    assert client.post("/api/auth/login", json={"email": u["email"], "password": PASSWORD}).status_code == 200


def test_last_admin_cannot_delete_account(client, dsn, conn):
    # Demote every other admin so this one is the last.
    admin = make_user(client, dsn, admin=True)
    conn.execute("UPDATE users SET role = 'user' WHERE role = 'admin' AND id <> %s", (admin["id"],))
    conn.commit()
    r = client.request("DELETE", "/api/users/me", json={"password": PASSWORD}, headers=admin["headers"])
    assert r.status_code == 409
    assert client.get("/api/users/me", headers=admin["headers"]).status_code == 200


def test_delete_password_attempts_are_rate_limited(client):
    u = make_user(client)
    for _ in range(5):
        client.request(
            "DELETE", "/api/users/me", json={"password": "wrong wrong wrong"}, headers=u["headers"]
        )
    r = client.request("DELETE", "/api/users/me", json={"password": PASSWORD}, headers=u["headers"])
    assert r.status_code == 429
