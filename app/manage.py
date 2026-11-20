"""Operator commands, run with direct database access (never exposed over HTTP).

Bootstrapping the first administrator is deliberately not an API feature: only an admin can
promote someone via the API, so the first one must come from someone who already controls
the server.

    docker compose exec api python -m app.manage promote-admin someone@example.com
"""

import argparse
import sys

import psycopg
from psycopg.rows import dict_row


def promote_admin(dsn: str, email: str) -> bool:
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "UPDATE users SET role = 'admin' WHERE email = %s AND deleted_at IS NULL RETURNING id",
            (email,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "INSERT INTO audit_log (actor_id, action, target_type, target_id) "
            "VALUES (NULL, 'admin.bootstrap_promote', 'user', %s)",
            (str(row["id"]),),
        )
    return True


def main() -> None:
    from app.config import get_settings

    ap = argparse.ArgumentParser(description="GeoVault operator commands")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("promote-admin", help="grant the admin role to an existing account")
    p.add_argument("email")
    args = ap.parse_args()

    dsn = get_settings().database_url.get_secret_value()
    if args.cmd == "promote-admin":
        if not promote_admin(dsn, args.email):
            sys.exit("No active account with that email.")
        print("Promoted.")


if __name__ == "__main__":
    main()
