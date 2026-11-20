"""Sharing: with a registered user or via an expiring link.

Every non-owner read goes through _SHARED_SELECT, which cloaks coordinates in SQL and
selects no note, email, place link or exact geometry. A share is only honoured while:
not revoked, not expired, the favourite is not 'private', and the owner is not deleted.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg import Connection

from app.security.tokens import sha256_token

MAX_ACTIVE_SHARES_PER_FAVOURITE = 50


class ShareError(Exception):
    status = 409


class PrivateFavourite(ShareError):
    def __str__(self):
        return "This favourite is private. Set its visibility to 'shared' or 'public' first."


class RecipientNotFound(ShareError):
    status = 404

    def __str__(self):
        return "No active account with that email address."


class SelfShare(ShareError):
    status = 422

    def __str__(self):
        return "You cannot share a favourite with yourself."


class AlreadyShared(ShareError):
    def __str__(self):
        return "This favourite is already shared with that user."


class TooManyShares(ShareError):
    def __str__(self):
        return f"A favourite can have at most {MAX_ACTIVE_SHARES_PER_FAVOURITE} active shares."


_SHARED_SELECT = """
    SELECT s.id AS share_id, f.label, f.region, f.share_precision_m AS precision_m,
           ST_Y(c.p) AS lat, ST_X(c.p) AS lon,
           o.display_name AS owner_display_name, s.created_at AS shared_at, s.expires_at,
           EXISTS (SELECT 1 FROM photos ph WHERE ph.favourite_id = f.id) AS has_photo,
           f.id AS favourite_id
    FROM shares s
    JOIN favourites f ON f.id = s.favourite_id
    JOIN users o ON o.id = f.owner_id AND o.deleted_at IS NULL
    JOIN regions r ON r.code = f.region
    CROSS JOIN LATERAL (SELECT cloak_point(f.geom, r.local_srid, f.share_precision_m) AS p) c
    WHERE s.revoked_at IS NULL
      AND (s.expires_at IS NULL OR s.expires_at > now())
      AND f.visibility <> 'private'
"""

_SHARE_COLUMNS = """
    s.id, CASE WHEN s.share_token_hash IS NULL THEN 'user' ELSE 'link' END AS type,
    u.display_name AS recipient_display_name, s.expires_at, s.revoked_at, s.created_at
"""


def to_shared_out(row: dict) -> dict:
    return {
        **row,
        # Rounded: 14 decimal places on a cell centre would imply a precision it does not have.
        "location": {
            "lat": round(row["lat"], 6),
            "lon": round(row["lon"], 6),
            "precision_m": row["precision_m"],
        },
    }


def _check_shareable(conn: Connection, favourite_id: uuid.UUID) -> None:
    fav = conn.execute(
        "SELECT visibility FROM favourites WHERE id = %s FOR UPDATE", (favourite_id,)
    ).fetchone()
    if fav["visibility"] == "private":
        raise PrivateFavourite
    active = conn.execute(
        "SELECT count(*) AS n FROM shares WHERE favourite_id = %s AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > now())",
        (favourite_id,),
    ).fetchone()
    if active["n"] >= MAX_ACTIVE_SHARES_PER_FAVOURITE:
        raise TooManyShares


def _expiry(hours: int | None) -> datetime | None:
    return datetime.now(UTC) + timedelta(hours=hours) if hours else None


def share_with_user(
    conn: Connection, favourite_id: uuid.UUID, owner_id: uuid.UUID, email: str, hours: int | None
) -> dict:
    _check_shareable(conn, favourite_id)
    recipient = conn.execute(
        "SELECT id FROM users WHERE email = %s AND deleted_at IS NULL", (email,)
    ).fetchone()
    if recipient is None:
        raise RecipientNotFound
    if recipient["id"] == owner_id:
        raise SelfShare
    try:
        with conn.transaction():
            share_id = conn.execute(
                "INSERT INTO shares (favourite_id, shared_with_user_id, expires_at) "
                "VALUES (%s, %s, %s) RETURNING id",
                (favourite_id, recipient["id"], _expiry(hours)),
            ).fetchone()["id"]
    except psycopg.errors.UniqueViolation:
        raise AlreadyShared from None
    return get_share(conn, favourite_id, share_id)


def share_by_link(conn: Connection, favourite_id: uuid.UUID, hours: int) -> tuple[dict, str]:
    _check_shareable(conn, favourite_id)
    raw = secrets.token_urlsafe(32)  # 256 bits: unguessable; only its SHA-256 is stored
    share_id = conn.execute(
        "INSERT INTO shares (favourite_id, share_token_hash, expires_at) VALUES (%s, %s, %s) RETURNING id",
        (favourite_id, sha256_token(raw), _expiry(hours)),
    ).fetchone()["id"]
    return get_share(conn, favourite_id, share_id), raw


def get_share(conn: Connection, favourite_id: uuid.UUID, share_id: uuid.UUID) -> dict | None:
    return conn.execute(
        f"""
        SELECT {_SHARE_COLUMNS} FROM shares s LEFT JOIN users u ON u.id = s.shared_with_user_id
        WHERE s.id = %s AND s.favourite_id = %s
        """,  # noqa: S608 (constant column list)
        (share_id, favourite_id),
    ).fetchone()


def list_shares(conn: Connection, favourite_id: uuid.UUID) -> list[dict]:
    return conn.execute(
        f"""
        SELECT {_SHARE_COLUMNS} FROM shares s LEFT JOIN users u ON u.id = s.shared_with_user_id
        WHERE s.favourite_id = %s ORDER BY s.created_at DESC
        """,  # noqa: S608 (constant column list)
        (favourite_id,),
    ).fetchall()


def revoke(conn: Connection, favourite_id: uuid.UUID, share_id: uuid.UUID) -> bool:
    row = conn.execute(
        "UPDATE shares SET revoked_at = coalesce(revoked_at, now()) "
        "WHERE id = %s AND favourite_id = %s RETURNING id",
        (share_id, favourite_id),
    ).fetchone()
    return row is not None


def view_by_token(conn: Connection, raw: str) -> dict | None:
    return conn.execute(_SHARED_SELECT + " AND s.share_token_hash = %s", (sha256_token(raw),)).fetchone()


def received(conn: Connection, user_id: uuid.UUID) -> list[dict]:
    return conn.execute(
        _SHARED_SELECT + " AND s.shared_with_user_id = %s ORDER BY s.created_at DESC",
        (user_id,),
    ).fetchall()
