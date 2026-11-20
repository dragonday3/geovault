"""Admin endpoints: function-level authorization (OWASP API5), role management, audit view.

The LAB-05 lab variant will remove the server-side role check; these are the secure-mode
regression tests that prove it is present.
"""

import uuid

import pytest

from app.manage import promote_admin
from tests.helpers import make_user

ADMIN_CALLS = [
    ("GET", "/api/admin/users", None),
    ("PATCH", "/api/admin/users/{target}/role", {"role": "admin"}),
    ("GET", "/api/admin/audit", None),
]


@pytest.mark.parametrize("method, path, body", ADMIN_CALLS)
def test_admin_routes_reject_anonymous(client, method, path, body):
    r = client.request(method, path.format(target=uuid.uuid4()), json=body)
    assert r.status_code == 401


@pytest.mark.parametrize("method, path, body", ADMIN_CALLS)
def test_admin_routes_reject_ordinary_users(client, method, path, body):
    user = make_user(client)
    r = client.request(method, path.format(target=user["id"]), json=body, headers=user["headers"])
    assert r.status_code == 403
    me = client.get("/api/users/me", headers=user["headers"]).json()
    assert me["role"] == "user"  # self-promotion attempt changed nothing


def test_every_admin_route_is_protected():
    """Guard against a future admin route being added without the router-level dependency."""
    from app.deps import require_admin
    from app.routers.admin import router

    assert any(d.dependency is require_admin for d in router.dependencies)


def test_admin_lists_users(client, dsn):
    admin = make_user(client, dsn, admin=True)
    target = make_user(client, display_name="Findable Person")
    r = client.get("/api/admin/users", params={"q": "Findable"}, headers=admin["headers"])
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert [u["email"] for u in r.json()] == [target["email"]]
    assert "password_hash" not in r.text


def test_role_change_takes_effect_immediately_and_is_audited(client, dsn, conn):
    admin = make_user(client, dsn, admin=True)
    target = make_user(client)
    assert client.get("/api/admin/users", headers=target["headers"]).status_code == 403

    r = client.patch(
        f"/api/admin/users/{target['id']}/role", json={"role": "admin"}, headers=admin["headers"]
    )
    assert r.status_code == 200 and r.json()["role"] == "admin"
    # Same access token, new role: authorization reads the DB, not the token.
    assert client.get("/api/admin/users", headers=target["headers"]).status_code == 200

    client.patch(f"/api/admin/users/{target['id']}/role", json={"role": "user"}, headers=admin["headers"])
    assert client.get("/api/admin/users", headers=target["headers"]).status_code == 403

    actions = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE actor_id = %s AND target_id = %s ORDER BY id",
            (admin["id"], target["id"]),
        )
    ]
    assert actions == ["admin.role_grant_admin", "admin.role_revoke_admin"]


def test_admin_cannot_change_own_role(client, dsn):
    admin = make_user(client, dsn, admin=True)
    r = client.patch(f"/api/admin/users/{admin['id']}/role", json={"role": "user"}, headers=admin["headers"])
    assert r.status_code == 409


@pytest.mark.parametrize("body", [{"role": "superuser"}, {"role": "admin", "email": "x@example.com"}, {}])
def test_role_change_validates_input(client, dsn, body):
    admin = make_user(client, dsn, admin=True)
    target = make_user(client)
    r = client.patch(f"/api/admin/users/{target['id']}/role", json=body, headers=admin["headers"])
    assert r.status_code == 422


def test_role_change_unknown_user_is_404(client, dsn):
    admin = make_user(client, dsn, admin=True)
    r = client.patch(
        f"/api/admin/users/{uuid.uuid4()}/role", json={"role": "admin"}, headers=admin["headers"]
    )
    assert r.status_code == 404


def test_audit_view_filters_and_is_itself_audited(client, dsn):
    admin = make_user(client, dsn, admin=True)
    r = client.get(
        "/api/admin/audit", params={"action": "auth", "actor_id": admin["id"]}, headers=admin["headers"]
    )
    assert r.status_code == 200
    entries = r.json()
    assert entries and all(e["action"].startswith("auth.") for e in entries)
    assert {"auth.register", "auth.login_success"} <= {e["action"] for e in entries}

    again = client.get(
        "/api/admin/audit", params={"action": "admin.audit_view"}, headers=admin["headers"]
    ).json()
    assert any(e["actor_id"] == admin["id"] for e in again)


def test_audit_filter_rejects_injection_shaped_input(client, dsn):
    admin = make_user(client, dsn, admin=True)
    r = client.get("/api/admin/audit", params={"action": "auth' OR '1'='1"}, headers=admin["headers"])
    assert r.status_code == 422


def test_bootstrap_promotion_is_audited(client, dsn, conn):
    u = make_user(client)
    assert promote_admin(dsn, u["email"])
    row = conn.execute(
        "SELECT actor_id FROM audit_log WHERE action = 'admin.bootstrap_promote' AND target_id = %s",
        (u["id"],),
    ).fetchone()
    assert row == (None,)
    assert not promote_admin(dsn, "nobody-here@example.com")
