"""Security audit events, written to audit_log in the caller's transaction.

Only identifiers go in: action, actor id, target type/id, client IP and user agent.
Callers must never pass passwords, tokens, notes, coordinates or attempted email addresses
(a mistyped password often lands in the email field).
"""

import ipaddress
import uuid

from fastapi import Request
from psycopg import Connection


def client_ip(request: Request) -> str:
    """Client address used for rate-limit keys (may be a non-IP label in tests)."""
    return request.client.host if request.client else "unknown"


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def audit(
    conn: Connection,
    request: Request,
    action: str,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (actor_id, action, target_type, target_id, ip, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            actor_id,
            action,
            target_type,
            str(target_id) if target_id is not None else None,
            _valid_ip(client_ip(request)),
            (request.headers.get("user-agent") or "")[:300] or None,
        ),
    )
