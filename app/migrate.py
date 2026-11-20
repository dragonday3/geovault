"""Minimal numbered-SQL migration runner.

Applies db/migrations/NNNN_name.sql files in order, each in its own transaction,
recording them in schema_migrations. A Postgres advisory lock serialises concurrent
starts. Run standalone with:  python -m app.migrate
"""

import logging
import re
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)

_NAME = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
_LOCK_ID = 7_421_001  # arbitrary, unique to GeoVault migrations


def pending(conn: psycopg.Connection, migrations_dir: Path) -> list[Path]:
    files = sorted(p for p in migrations_dir.glob("*.sql"))
    bad = [p.name for p in files if not _NAME.match(p.name)]
    if bad:
        raise RuntimeError(f"Unexpected migration file names: {bad}")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    return [p for p in files if p.stem not in applied]


def apply(dsn: str, migrations_dir: Path) -> list[str]:
    done: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_ID,))
        try:
            for path in pending(conn, migrations_dir):
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
                log.info("applied migration %s", path.stem)
                done.append(path.stem)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))
    return done


if __name__ == "__main__":
    from app.config import get_settings

    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    print(apply(s.database_url.get_secret_value(), s.migrations_dir) or "up to date")
