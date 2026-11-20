"""Authentication: registration, login, token validation, refresh rotation, logout, audit.

These are the secure-mode controls that the LAB-02 (broken authentication) and LAB-03
(mass assignment) lab variants will deliberately remove.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import psycopg
import pytest

from app.routers.auth import CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE

PASSWORD = "correct horse battery staple 42"


def new_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def register(client, email, password=PASSWORD, display_name="Test User"):
    return client.post(
        "/api/auth/register", json={"email": email, "password": password, "display_name": display_name}
    )


def login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def signed_in(client):
    email = new_email()
    assert register(client, email).status_code == 202
    r = login(client, email)
    assert r.status_code == 200, r.text
    return email, r.json()["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def csrf_headers(client):
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}


def set_cookie_headers(resp) -> list[str]:
    return resp.headers.get_list("set-cookie")


# --- registration --------------------------------------------------------------------------


def test_register_then_login(client):
    email, token = signed_in(client)
    me = client.get("/api/users/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == email and me.json()["role"] == "user"
    assert me.headers["cache-control"] == "no-store"


def test_duplicate_registration_is_indistinguishable(client):
    email = new_email()
    first, second = register(client, email), register(client, email.upper())  # citext: same email
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()  # no "email already exists" oracle


def test_email_is_case_insensitive_unique(client, conn):
    email = new_email()
    register(client, email)
    register(client, email.upper(), display_name="Imposter")
    n = conn.execute("SELECT count(*) FROM users WHERE email = %s", (email,)).fetchone()[0]
    assert n == 1


@pytest.mark.parametrize(
    "password, reason",
    [
        ("short-pw-1", "at least 12"),
        ("passwordpassword", "data breaches"),
        ("zqxzqxzqxzqxzqx", "repetitive"),
    ],
)
def test_password_policy(client, password, reason):
    r = register(client, new_email(), password=password)
    assert r.status_code == 422
    assert reason in r.text
    assert password not in r.text  # the rejected password is never echoed back


def test_password_must_not_contain_email(client):
    r = register(client, "kairuphantom@example.com", password="kairuphantom-is-my-name!")
    assert r.status_code == 422 and "email" in r.text


def test_register_rejects_extra_fields_mass_assignment(client, conn):
    email = new_email()
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Eve", "role": "admin"},
    )
    assert r.status_code == 422
    assert conn.execute("SELECT count(*) FROM users WHERE email = %s", (email,)).fetchone()[0] == 0


def test_register_rejects_markup_in_display_name(client):
    assert register(client, new_email(), display_name="<script>x</script>").status_code == 422


def test_register_is_rate_limited_per_client(client):
    statuses = [register(client, new_email()).status_code for _ in range(11)]
    assert statuses[:10] == [202] * 10 and statuses[10] == 429


# --- login ---------------------------------------------------------------------------------


def test_login_sets_hardened_cookies(client):
    email = new_email()
    register(client, email)
    r = login(client, email)
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 15 * 60
    assert r.headers["cache-control"] == "no-store"

    cookies = {c.split("=", 1)[0]: c.lower() for c in set_cookie_headers(r)}
    refresh = cookies[REFRESH_COOKIE]
    assert "httponly" in refresh and "secure" in refresh and "samesite=strict" in refresh
    assert "path=/api/auth" in refresh
    csrf = cookies[CSRF_COOKIE]
    assert "secure" in csrf and "samesite=strict" in csrf and "path=/" in csrf
    assert "httponly" not in csrf  # the frontend must read it to send the header
    assert REFRESH_COOKIE not in r.text  # refresh token never in the JSON body


def test_login_failure_is_generic(client):
    email = new_email()
    register(client, email)
    wrong_pw = login(client, email, "definitely not the password")
    unknown = login(client, new_email())
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()  # no user-enumeration oracle


def test_unknown_email_still_runs_argon2(client, monkeypatch):
    """Timing parity: an unknown email must cost one Argon2 verification, like a real one."""
    from app.services import auth as svc

    calls = []
    real = svc.verify_password
    monkeypatch.setattr(svc, "verify_password", lambda h, p: calls.append(h) or real(h, p))
    login(client, new_email())
    assert calls == [svc.DUMMY_HASH]


def test_login_rate_limited_per_account(client):
    email = new_email()
    register(client, email)
    for _ in range(5):
        assert login(client, email, "wrong password attempt").status_code == 401
    blocked = login(client, email)  # even the CORRECT password is refused while locked
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


# --- access tokens -------------------------------------------------------------------------


def _forge(sub, secret, **overrides):
    now = datetime.now(UTC)
    claims = {
        "sub": str(sub),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "iss": "geovault",
        "aud": "geovault-api",
        "typ": "access",
    } | overrides
    return jwt.encode(claims, secret, algorithm="HS256")


def test_protected_endpoint_requires_token(client):
    r = client.get("/api/users/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_rejects_tampered_and_malformed_tokens(client, conn):
    _, token = signed_in(client)
    header, payload, sig = token.split(".")
    tampered = f"{header}.{payload}.{sig[:-4]}AAAA"
    for bad in (tampered, "not.a.jwt", "", token + "x"):
        assert client.get("/api/users/me", headers=bearer(bad)).status_code == 401


def test_rejects_alg_none_token(client, conn):
    _, token = signed_in(client)
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    unsigned = jwt.encode(
        {
            "sub": sub,
            "iss": "geovault",
            "aud": "geovault-api",
            "typ": "access",
            "iat": 1,
            "nbf": 1,
            "exp": 9999999999,
        },
        key=None,
        algorithm="none",
    )
    assert client.get("/api/users/me", headers=bearer(unsigned)).status_code == 401


def test_rejects_token_signed_with_other_key(client):
    _, token = signed_in(client)
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    forged = _forge(sub, "x" * 64)
    assert client.get("/api/users/me", headers=bearer(forged)).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},  # expired
        {"aud": "someone-else"},  # wrong audience
        {"iss": "attacker"},  # wrong issuer
        {"typ": "refresh"},  # wrong token type
    ],
)
def test_rejects_invalid_claims_even_with_valid_signature(client, overrides):
    _, token = signed_in(client)
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    secret = client.app.state.settings.jwt_secret.get_secret_value()
    assert client.get("/api/users/me", headers=bearer(_forge(sub, secret, **overrides))).status_code == 401


def test_role_claim_in_token_is_ignored(client):
    """Authorization reads the role from the DB, so a forged role claim grants nothing."""
    _, token = signed_in(client)
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    secret = client.app.state.settings.jwt_secret.get_secret_value()
    r = client.get("/api/users/me", headers=bearer(_forge(sub, secret, role="admin")))
    assert r.status_code == 200 and r.json()["role"] == "user"


def test_token_for_deleted_user_is_rejected(client, dsn):
    _, token = signed_in(client)
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    with psycopg.connect(dsn) as c:
        c.execute("UPDATE users SET deleted_at = now() WHERE id = %s", (sub,))
    assert client.get("/api/users/me", headers=bearer(token)).status_code == 401


# --- refresh rotation ----------------------------------------------------------------------


def test_refresh_requires_csrf_header(client):
    signed_in(client)
    assert client.post("/api/auth/refresh").status_code == 403
    assert client.post("/api/auth/refresh", headers={CSRF_HEADER: "wrong"}).status_code == 403


def test_refresh_rotates_token(client):
    signed_in(client)
    old = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    r = client.post("/api/auth/refresh", headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    new = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    assert new and new != old
    assert client.get("/api/users/me", headers=bearer(r.json()["access_token"])).status_code == 200


def test_refresh_token_reuse_revokes_whole_family(client):
    signed_in(client)
    stolen = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    assert client.post("/api/auth/refresh", headers=csrf_headers(client)).status_code == 200  # legit rotation
    legit_new = client.cookies.get(REFRESH_COOKIE, path="/api/auth")

    # Attacker replays the stolen (already rotated) token.
    csrf = client.cookies.get(CSRF_COOKIE)
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, stolen, path="/api/auth")
    client.cookies.set(CSRF_COOKIE, csrf, path="/")
    replay = client.post("/api/auth/refresh", headers={CSRF_HEADER: csrf})
    assert replay.status_code == 401

    # The legitimate user's newest token is now dead too: the family was revoked.
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, legit_new, path="/api/auth")
    client.cookies.set(CSRF_COOKIE, csrf, path="/")
    assert client.post("/api/auth/refresh", headers={CSRF_HEADER: csrf}).status_code == 401


def test_expired_refresh_token_rejected(client, dsn):
    signed_in(client)
    raw = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    with psycopg.connect(dsn) as c:
        c.execute(
            "UPDATE refresh_tokens SET created_at = now() - interval '30 days', "
            "expires_at = now() - interval '1 second' WHERE token_hash = %s",
            (hashlib.sha256(raw.encode()).digest(),),
        )
    assert client.post("/api/auth/refresh", headers=csrf_headers(client)).status_code == 401


def test_refresh_tokens_are_stored_hashed(client, conn):
    signed_in(client)
    raw = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    row = conn.execute(
        "SELECT token_hash FROM refresh_tokens WHERE token_hash = %s",
        (hashlib.sha256(raw.encode()).digest(),),
    ).fetchone()
    assert row is not None
    leaked = conn.execute(
        "SELECT count(*) FROM refresh_tokens WHERE encode(token_hash, 'escape') LIKE %s", (f"%{raw}%",)
    ).fetchone()[0]
    assert leaked == 0


# --- logout --------------------------------------------------------------------------------


def test_logout_revokes_session(client):
    signed_in(client)
    csrf = csrf_headers(client)
    raw = client.cookies.get(REFRESH_COOKIE, path="/api/auth")
    r = client.post("/api/auth/logout", headers=csrf)
    assert r.status_code == 204
    assert any("gv_refresh=" in c and "max-age=0" in c.lower() for c in set_cookie_headers(r))

    client.cookies.set(REFRESH_COOKIE, raw, path="/api/auth")
    client.cookies.set(CSRF_COOKIE, csrf[CSRF_HEADER], path="/")
    assert client.post("/api/auth/refresh", headers=csrf).status_code == 401


def test_logout_requires_csrf(client):
    signed_in(client)
    assert client.post("/api/auth/logout").status_code == 403


# --- audit ---------------------------------------------------------------------------------


def test_auth_events_are_audited_without_secrets(client, conn):
    email = new_email()
    register(client, email)
    login(client, email, "wrong password here")
    login(client, new_email(), "another wrong one")
    login(client, email)
    user_id = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()[0]

    actions = [
        r[0]
        for r in conn.execute(
            "SELECT action FROM audit_log WHERE actor_id = %s OR target_id = %s ORDER BY id",
            (user_id, str(user_id)),
        )
    ]
    assert actions == ["auth.register", "auth.login_failure", "auth.login_success"]

    dump = " ".join(str(v) for row in conn.execute("SELECT * FROM audit_log").fetchall() for v in row)
    for secret in (PASSWORD, "wrong password here", "another wrong one", email):
        assert secret not in dump
