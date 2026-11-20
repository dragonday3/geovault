"""Shared fixtures. Tests run against a real PostGIS database, never mocks: the security
properties under test (bound parameters, DB constraints, role privileges) only exist there.

Safety rail: tests write and delete data, so they refuse to run unless the database host
is a dedicated local test instance. They can never touch the dev DB (`db`) or anything remote.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_TEST_DB_HOSTS = {"localhost", "127.0.0.1", "db-test"}


def _test_dsn() -> str:
    dsn = os.environ.get("GEOVAULT_DATABASE_URL")
    if not dsn:
        pytest.exit("GEOVAULT_DATABASE_URL is not set", returncode=2)
    host = urlparse(dsn).hostname
    if host not in ALLOWED_TEST_DB_HOSTS:
        pytest.exit(
            f"Refusing to run tests against database host {host!r}; allowed: {sorted(ALLOWED_TEST_DB_HOSTS)}",
            returncode=2,
        )
    return dsn


@pytest.fixture(scope="session")
def dsn() -> str:
    return _test_dsn()


@pytest.fixture(scope="session")
def client(dsn):
    """App with migrations applied (lifespan runs on enter) and the sample seed loaded."""
    from app.config import Settings
    from app.main import create_app
    from load_places import load

    app = create_app(Settings(database_url=dsn, env="local"))
    # https base URL: the session cookies are Secure, and like a browser the client only
    # sends Secure cookies over HTTPS.
    with TestClient(app, base_url="https://testserver") as c:
        for region in ("melbourne", "bengaluru"):
            load(
                str(ROOT / "data" / "samples" / f"{region}.geojson"),
                region,
                "sample",
                "id",
                "name",
                "category",
                None,
                dsn,
            )
        yield c


@pytest.fixture
def conn(dsn, client):
    """Direct connection as the application role; rolled back after each test."""
    with psycopg.connect(dsn) as c:
        yield c
        c.rollback()


@pytest.fixture(autouse=True)
def _reset_rate_limiters(client):
    """Rate-limit state is per process; isolate tests from each other's attempts."""
    client.app.state.login_limiter.account.reset()
    client.app.state.login_limiter.ip.reset()
    client.app.state.register_limiter.reset()
    client.app.state.share_limiter.reset()
    client.cookies.clear()
