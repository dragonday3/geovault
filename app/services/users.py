"""Account lifecycle: profile edits, data export, account deletion, role changes.

Deletion model (privacy: APP 11.2 / DPDP s.8(7) erasure):
  * personal content is DELETED: favourites (cascading shares + photos), shares received,
    refresh tokens;
  * the users row is ANONYMISED in place: email, name and password hash are replaced and
    deleted_at is set. The id survives only so existing audit rows still resolve to
    "Deleted user" for security investigations. It carries no personal information;
  * audit_log rows are RETAINED as security evidence. They hold no names, emails or content,
    and IP addresses age out under the retention job (privacy controls, project 3).
"""

import uuid
from datetime import UTC, datetime

from psycopg import Connection

ANONYMISED_NAME = "Deleted user"
DELETED_HASH = "!deleted"  # allowed by the users.password_hash CHECK; can never verify


class LastAdminError(Exception):
    pass


def update_display_name(conn: Connection, user_id: uuid.UUID, display_name: str) -> dict:
    return conn.execute(
        """
        UPDATE users SET display_name = %s WHERE id = %s AND deleted_at IS NULL
        RETURNING id, email, display_name, role, created_at
        """,
        (display_name, user_id),
    ).fetchone()


def _other_active_admins(conn: Connection, user_id: uuid.UUID) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM users WHERE role = 'admin' AND deleted_at IS NULL AND id <> %s",
        (user_id,),
    ).fetchone()["n"]


def delete_account(conn: Connection, user_id: uuid.UUID) -> None:
    role = conn.execute("SELECT role FROM users WHERE id = %s FOR UPDATE", (user_id,)).fetchone()["role"]
    if role == "admin" and _other_active_admins(conn, user_id) == 0:
        raise LastAdminError("The last administrator cannot delete their account.")

    conn.execute("DELETE FROM favourites WHERE owner_id = %s", (user_id,))  # cascades shares, photos
    conn.execute("DELETE FROM shares WHERE shared_with_user_id = %s", (user_id,))
    conn.execute("DELETE FROM refresh_tokens WHERE user_id = %s", (user_id,))
    conn.execute(
        """
        UPDATE users
           SET email = 'deleted-' || id || '@invalid',
               display_name = %s,
               password_hash = %s,
               role = 'user',
               last_login_at = NULL,
               deleted_at = now()
         WHERE id = %s
        """,
        (ANONYMISED_NAME, DELETED_HASH, user_id),
    )


def export_data(conn: Connection, user_id: uuid.UUID) -> dict:
    """Everything GeoVault holds about the user, in a portable JSON structure.

    Includes the user's own exact coordinates and notes (it is their data). Excludes
    secrets (password hash, token hashes) and other people's personal information:
    share recipients appear by display name only, never by email.
    """
    profile = conn.execute(
        "SELECT id, email, display_name, role, created_at, last_login_at FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    favourites = conn.execute(
        """
        SELECT id, place_id, region, label, note, ST_Y(geom) AS lat, ST_X(geom) AS lon,
               visibility, share_precision_m, created_at, updated_at
        FROM favourites WHERE owner_id = %s ORDER BY created_at
        """,
        (user_id,),
    ).fetchall()
    shares_created = conn.execute(
        """
        SELECT s.id, s.favourite_id,
               CASE WHEN s.share_token_hash IS NULL THEN 'user' ELSE 'link' END AS kind,
               r.display_name AS recipient_display_name,
               s.expires_at, s.revoked_at, s.created_at
        FROM shares s JOIN favourites f ON f.id = s.favourite_id
        LEFT JOIN users r ON r.id = s.shared_with_user_id
        WHERE f.owner_id = %s ORDER BY s.created_at
        """,
        (user_id,),
    ).fetchall()
    shares_received = conn.execute(
        """
        SELECT s.id, f.label AS favourite_label, o.display_name AS owner_display_name,
               s.expires_at, s.revoked_at, s.created_at
        FROM shares s JOIN favourites f ON f.id = s.favourite_id JOIN users o ON o.id = f.owner_id
        WHERE s.shared_with_user_id = %s ORDER BY s.created_at
        """,
        (user_id,),
    ).fetchall()
    photos = conn.execute(
        """
        SELECT p.id, p.favourite_id, p.content_type, p.size_bytes, p.created_at
        FROM photos p JOIN favourites f ON f.id = p.favourite_id
        WHERE f.owner_id = %s ORDER BY p.created_at
        """,
        (user_id,),
    ).fetchall()
    sessions = conn.execute(
        """
        SELECT created_at, expires_at, revoked_at FROM refresh_tokens
        WHERE user_id = %s ORDER BY created_at
        """,
        (user_id,),
    ).fetchall()
    activity = conn.execute(
        """
        SELECT action, target_type, target_id, host(ip) AS ip, user_agent, created_at
        FROM audit_log WHERE actor_id = %s ORDER BY id
        """,
        (user_id,),
    ).fetchall()
    return {
        "format": "geovault-export/1",
        "exported_at": datetime.now(UTC),
        "profile": profile,
        "favourites": favourites,
        "shares_created": shares_created,
        "shares_received": shares_received,
        "photos": photos,
        "sessions": sessions,
        "activity": activity,
    }


def set_role(conn: Connection, user_id: uuid.UUID, role: str) -> tuple[dict | None, str | None]:
    """Change a user's role. Returns (updated row, previous role) or (None, None) if not found."""
    prev = conn.execute(
        "SELECT role FROM users WHERE id = %s AND deleted_at IS NULL FOR UPDATE", (user_id,)
    ).fetchone()
    if prev is None:
        return None, None
    row = conn.execute(
        """
        UPDATE users SET role = %s WHERE id = %s
        RETURNING id, email, display_name, role, created_at, last_login_at, deleted_at
        """,
        (role, user_id),
    ).fetchone()
    return row, prev["role"]
