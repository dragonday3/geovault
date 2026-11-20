"""Authentication business logic: registration, credential check, refresh-token rotation."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg import Connection

from app.security.passwords import DUMMY_HASH, hash_password, needs_rehash, verify_password
from app.security.tokens import hash_refresh_token, new_refresh_token


class InvalidRefreshToken(Exception):
    pass


class RefreshTokenReuse(Exception):
    """An already-rotated refresh token was presented: it was copied, so assume theft."""

    def __init__(self, user_id: uuid.UUID):
        self.user_id = user_id


@dataclass
class LoginResult:
    user_id: uuid.UUID | None  # set only on success
    known_account_id: uuid.UUID | None  # for the audit trail on failure; never returned to client


def register(conn: Connection, email: str, password: str, display_name: str) -> uuid.UUID | None:
    """Create the account; return its id, or None if the email is already registered.

    The password is hashed BEFORE the uniqueness check, so a duplicate registration costs
    exactly as much time as a new one (no timing signal that the email exists).
    """
    pw_hash = hash_password(password)
    row = conn.execute(
        """
        INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s)
        ON CONFLICT (email) DO NOTHING
        RETURNING id
        """,
        (email, pw_hash, display_name),
    ).fetchone()
    return row["id"] if row else None


def authenticate(conn: Connection, email: str, password: str) -> LoginResult:
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE email = %s AND deleted_at IS NULL",
        (email,),
    ).fetchone()
    if row is None:
        verify_password(DUMMY_HASH, password)  # same Argon2 cost as a real check
        return LoginResult(None, None)
    if not verify_password(row["password_hash"], password):
        return LoginResult(None, row["id"])
    if needs_rehash(row["password_hash"]):  # transparently upgrade old hash parameters
        conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(password), row["id"])
        )
    conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row["id"],))
    return LoginResult(row["id"], row["id"])


def issue_refresh_token(
    conn: Connection, user_id: uuid.UUID, days: int, family_id: uuid.UUID | None = None
) -> tuple[str, uuid.UUID]:
    raw, digest = new_refresh_token()
    row = conn.execute(
        """
        INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at)
        VALUES (%s, %s, %s, %s) RETURNING id
        """,
        (user_id, family_id or uuid.uuid4(), digest, datetime.now(UTC) + timedelta(days=days)),
    ).fetchone()
    return raw, row["id"]


def _revoke_family(conn: Connection, family_id: uuid.UUID) -> None:
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at = now() WHERE family_id = %s AND revoked_at IS NULL",
        (family_id,),
    )


def rotate_refresh_token(conn: Connection, raw: str, days: int) -> tuple[uuid.UUID, str]:
    """Exchange a valid refresh token for a new one. Returns (user_id, new raw token).

    FOR UPDATE serialises concurrent refreshes of the same token: the loser sees it as
    already revoked and is treated as reuse. Trade-off: two tabs refreshing at the exact
    same instant log the session out (safe failure).
    """
    row = conn.execute(
        """
        SELECT t.id, t.user_id, t.family_id, t.expires_at, t.revoked_at, u.deleted_at
        FROM refresh_tokens t JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = %s
        FOR UPDATE OF t
        """,
        (hash_refresh_token(raw),),
    ).fetchone()
    if row is None:
        raise InvalidRefreshToken("unknown token")
    if row["revoked_at"] is not None:
        _revoke_family(conn, row["family_id"])
        raise RefreshTokenReuse(row["user_id"])
    if row["expires_at"] <= datetime.now(UTC) or row["deleted_at"] is not None:
        _revoke_family(conn, row["family_id"])
        raise InvalidRefreshToken("expired or account deleted")

    new_raw, new_id = issue_refresh_token(conn, row["user_id"], days, row["family_id"])
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at = now(), replaced_by = %s WHERE id = %s",
        (new_id, row["id"]),
    )
    return row["user_id"], new_raw


def revoke_session(conn: Connection, raw: str) -> uuid.UUID | None:
    """Logout: revoke the presented token's whole family. Returns the user id if known."""
    row = conn.execute(
        "SELECT user_id, family_id FROM refresh_tokens WHERE token_hash = %s",
        (hash_refresh_token(raw),),
    ).fetchone()
    if row is None:
        return None
    _revoke_family(conn, row["family_id"])
    return row["user_id"]
