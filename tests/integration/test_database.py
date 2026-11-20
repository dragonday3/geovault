"""Database-level guarantees: least privilege, constraints, migrations."""

import psycopg
import pytest

from app import migrate


def test_app_role_is_least_privilege(conn):
    row = conn.execute(
        "SELECT rolsuper, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row == (False, False, False)


def test_app_role_cannot_read_server_files(conn):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT pg_read_file('/etc/passwd', 0, 10)")


def test_trigger_rejects_place_outside_its_region(conn):
    # Melbourne coordinates labelled as Bengaluru.
    with pytest.raises(psycopg.errors.CheckViolation, match="outside region bengaluru"):
        conn.execute(
            "INSERT INTO places (region, source, source_id, name, category, geom) VALUES "
            "('bengaluru', 'test', 't1', 'x', 'x', ST_SetSRID(ST_MakePoint(144.96, -37.81), 4326))"
        )


def test_trigger_rejects_moving_place_out_of_region(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE places SET geom = ST_SetSRID(ST_MakePoint(0, 0), 4326) "
            "WHERE id = (SELECT min(id) FROM places)"
        )


def test_unique_source_key(conn):
    conn.execute(
        "INSERT INTO places (region, source, source_id, name, category, geom) VALUES "
        "('melbourne', 'test', 'dup', 'a', 'x', ST_SetSRID(ST_MakePoint(144.96, -37.81), 4326))"
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO places (region, source, source_id, name, category, geom) VALUES "
            "('melbourne', 'test', 'dup', 'b', 'x', ST_SetSRID(ST_MakePoint(144.96, -37.81), 4326))"
        )


def test_migrations_are_idempotent(dsn, client):
    from app.config import Settings

    assert migrate.apply(dsn, Settings(database_url=dsn).migrations_dir) == []


def test_migration_runner_rejects_unexpected_file_names(dsn, client, tmp_path):
    (tmp_path / "0099_ok.sql").write_text("SELECT 1;")
    (tmp_path / "evil; DROP TABLE x.sql").write_text("SELECT 1;")
    with pytest.raises(RuntimeError, match="Unexpected migration file names"):
        migrate.apply(dsn, tmp_path)
