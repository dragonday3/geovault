"""Connection pool and per-request connection dependency."""

from collections.abc import Iterator

from fastapi import Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def create_pool(dsn: str) -> ConnectionPool:
    return ConnectionPool(
        dsn,
        min_size=1,
        max_size=10,
        open=False,
        # Cap every statement so a slow query cannot pin a worker indefinitely.
        kwargs={"row_factory": dict_row, "options": "-c statement_timeout=5000"},
    )


def get_conn(request: Request) -> Iterator[Connection]:
    """Yield a pooled connection. The pool commits on success and rolls back on error."""
    with request.app.state.pool.connection() as conn:
        yield conn
