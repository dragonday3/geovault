"""The GeoServer database role: the control that keeps WMS/WFS away from private data.

GeoServer itself is too heavy for CI; geoserver/verify.py checks the running service locally.
These tests pin the part that matters most and holds even if GeoServer is misconfigured:
geoserver_ro can read the public_places view and nothing else, and only read.
"""

import os
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest

PRIVATE = (
    "places",
    "users",
    "favourites",
    "shares",
    "photos",
    "refresh_tokens",
    "audit_log",
    "checkins_synthetic",
)


@pytest.fixture
def ro(dsn, client):
    parts = urlparse(dsn)
    password = os.environ["GEOVAULT_GEOSERVER_DB_PASSWORD"]
    ro_dsn = urlunparse(
        parts._replace(netloc=f"geoserver_ro:{password}@{parts.hostname}:{parts.port or 5432}")
    )
    with psycopg.connect(ro_dsn) as conn:
        yield conn


def test_role_is_not_privileged(ro):
    row = ro.execute(
        "SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row == (False, False, False)


def test_reads_public_places_with_public_columns_only(ro):
    assert ro.execute("SELECT count(*) FROM public_places").fetchone()[0] > 0
    cols = {
        r[0]
        for r in ro.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'public_places'"
        )
    }
    assert cols == {"id", "name", "category", "region", "source", "geom"}


@pytest.mark.parametrize("table", PRIVATE)
def test_cannot_read_any_other_table(ro, table):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        ro.execute(f"SELECT 1 FROM {table} LIMIT 1")  # noqa: S608 (constant table names)


def test_every_transaction_is_read_only(ro):
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        ro.execute("DELETE FROM public_places")


def test_only_grant_is_select_on_the_view(ro):
    grants = ro.execute(
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'geoserver_ro'"
    ).fetchall()
    assert grants == [("public_places", "SELECT")]
