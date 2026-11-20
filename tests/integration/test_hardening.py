"""HTTP hardening (OWASP API8 security misconfiguration): headers, CSP, CORS, error handling,
request IDs and log hygiene. The LAB-06 lab variant removes these controls."""

import io
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.observability import JsonFormatter
from tests.helpers import PASSWORD, make_user

ROOT = Path(__file__).resolve().parents[2]
EVIL = "https://evil.example"


@pytest.fixture
def logs():
    """Capture everything the app logs, formatted exactly as in production."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    # The TEST CLIENT's own HTTP library logs the URLs it requests; that is not server output.
    client_side = logging.getLogger("httpx")
    previous = client_side.level
    client_side.setLevel(logging.WARNING)
    yield buf
    client_side.setLevel(previous)
    root.removeHandler(handler)


def lines(buf) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


# --- headers ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/api/health", "/api/places?limit=1", "/api/users/me", "/api/nope"])
def test_security_headers_on_every_response(client, path):
    r = client.get(path)
    h = r.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin"
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in h["permissions-policy"]
    csp = h["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "server" not in {k.lower() for k in h}  # no software banner from the app


def test_api_responses_default_to_no_store(client):
    assert client.get("/api/places?limit=1").headers["cache-control"] == "no-store"


def test_route_specific_csp_is_not_overwritten(client):
    """The photo route's stricter sandbox CSP must survive the global middleware."""
    from tests import images

    u = make_user(client)
    fav = client.post(
        "/api/favourites",
        json={"label": "x", "location": {"lat": -37.81, "lon": 144.96}},
        headers=u["headers"],
    ).json()
    client.post(
        f"/api/favourites/{fav['id']}/photo",
        files={"file": ("a.jpg", images.jpeg_with_gps(), "image/jpeg")},
        headers=u["headers"],
    )
    r = client.get(f"/api/favourites/{fav['id']}/photo", headers=u["headers"])
    assert r.headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_relaxed_csp_only_on_local_docs(client):
    docs = client.get("/docs").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in docs
    assert "cdn.jsdelivr.net" not in client.get("/").headers["content-security-policy"]


def test_hsts_only_in_production(dsn):
    from app.config import Settings
    from app.main import create_app

    assert (
        "strict-transport-security" not in TestClient(create_app(Settings(database_url=dsn))).get("/").headers
    )
    prod = create_app(Settings(database_url=dsn, env="production"))
    with TestClient(prod, base_url="https://testserver") as c:
        assert c.get("/api/health").headers["strict-transport-security"].startswith("max-age=31536000")


def test_uvicorn_banner_and_raw_access_log_disabled():
    cmd = (ROOT / "app" / "Dockerfile").read_text()
    assert "--no-server-header" in cmd and "--no-access-log" in cmd


# --- CORS ----------------------------------------------------------------------------------------


def test_no_cors_for_foreign_origins(client):
    u = make_user(client)
    r = client.get("/api/users/me", headers=u["headers"] | {"Origin": EVIL})
    assert "access-control-allow-origin" not in r.headers
    pre = client.options(
        "/api/users/me",
        headers={
            "Origin": EVIL,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert "access-control-allow-origin" not in pre.headers
    assert "access-control-allow-credentials" not in pre.headers


# --- request IDs and errors -------------------------------------------------------------------------


def test_request_id_generated_or_safely_propagated(client):
    assert len(client.get("/api/health").headers["x-request-id"]) == 32
    assert (
        client.get("/api/health", headers={"X-Request-ID": "trace-abc12345"}).headers["x-request-id"]
        == "trace-abc12345"
    )
    forged = client.get("/api/health", headers={"X-Request-ID": "x\r\nSet-Cookie: pwn=1"}).headers[
        "x-request-id"
    ]
    assert forged != "x\r\nSet-Cookie: pwn=1" and len(forged) == 32


@pytest.fixture
def exploding_client(dsn):
    from fastapi.routing import APIRoute

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(database_url=dsn))

    def boom():
        raise RuntimeError("connect postgresql://geovault_app:hunter2@db/geovault failed; password=hunter2")

    app.router.routes.insert(0, APIRoute("/api/boom", boom))
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
        yield c


def test_unhandled_errors_are_generic_and_logged_safely(exploding_client, logs):
    r = exploding_client.get("/api/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error" and body["request_id"] == r.headers["x-request-id"]
    assert "Traceback" not in r.text and "hunter2" not in r.text and "RuntimeError" not in r.text
    assert r.headers["x-content-type-options"] == "nosniff"

    errors = [e for e in lines(logs) if e["logger"] == "geovault.error"]
    assert errors and errors[0]["request_id"] == body["request_id"]
    assert "RuntimeError" in errors[0]["exc"]  # full detail is in the server log...
    assert "hunter2" not in json.dumps(errors)  # ...with secrets scrubbed


# --- log hygiene across a full user journey --------------------------------------------------------


def test_logs_never_contain_secrets_or_locations(client, logs):
    note = "note-only-the-owner-knows-7731"
    u = make_user(client)
    fav = client.post(
        "/api/favourites",
        json={
            "label": "Home",
            "note": note,
            "location": {"lat": -37.81361, "lon": 144.96312},
            "visibility": "shared",
        },
        headers=u["headers"],
    ).json()
    share = client.post(
        f"/api/favourites/{fav['id']}/share", json={"type": "link"}, headers=u["headers"]
    ).json()
    client.get(share["path"])
    client.get("/api/places/near", params={"lat": -37.81361, "lon": 144.96312})
    client.post("/api/auth/login", json={"email": u["email"], "password": "wrong password attempt"})

    out = logs.getvalue()
    access = [e for e in lines(logs) if e["logger"] == "geovault.access"]
    assert access and all({"method", "path", "status", "duration_ms", "request_id"} <= set(e) for e in access)
    assert any(e["path"] == "/api/shared/[REDACTED]" for e in access)
    for leak in (
        PASSWORD,
        "wrong password attempt",
        u["email"],
        u["token"],
        note,
        share["token"],
        "-37.81361",
        "144.96312",
        "lat=",
        "lon=",
    ):
        assert leak not in out, leak
