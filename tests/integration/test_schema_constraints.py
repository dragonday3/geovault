"""Database constraints on private data: the last line of defence if app code is wrong."""

import psycopg
import pytest

MELB = "ST_SetSRID(ST_MakePoint(144.9631, -37.8136), 4326)"


@pytest.fixture
def user_and_fav(conn):
    uid = conn.execute(
        "INSERT INTO users (email, password_hash, display_name) "
        "VALUES (gen_random_uuid() || '@example.com', '$argon2id$v=19$x', 'T') RETURNING id"
    ).fetchone()[0]
    fid = conn.execute(
        f"INSERT INTO favourites (owner_id, region, label, geom) VALUES (%s, 'melbourne', 'Home', {MELB}) "  # noqa: S608 (constant)
        "RETURNING id",
        (uid,),
    ).fetchone()[0]
    return uid, fid


def test_user_password_must_be_argon2id(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO users (email, password_hash, display_name) "
            "VALUES ('p@example.com', 'plaintext', 'P')"
        )


def test_share_needs_exactly_one_target(conn, user_and_fav):
    uid, fid = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation, match="shares_exactly_one_target"):
        conn.execute("INSERT INTO shares (favourite_id) VALUES (%s)", (fid,))
    conn.rollback()


def test_share_cannot_be_both_user_and_link(conn, user_and_fav):
    uid, fid = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation, match="shares_exactly_one_target"):
        conn.execute(
            "INSERT INTO shares (favourite_id, shared_with_user_id, share_token_hash, expires_at) "
            "VALUES (%s, %s, sha256('t'), now() + interval '1 day')",
            (fid, uid),
        )


def test_link_share_must_expire(conn, user_and_fav):
    _, fid = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation, match="shares_links_expire"):
        conn.execute("INSERT INTO shares (favourite_id, share_token_hash) VALUES (%s, sha256('t'))", (fid,))


def test_share_precision_is_restricted(conn, user_and_fav):
    _, fid = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE favourites SET share_precision_m = 1 WHERE id = %s", (fid,))


def test_photo_must_be_exif_stripped_with_server_key(conn, user_and_fav):
    _, fid = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO photos (favourite_id, storage_key, exif_stripped, content_type, size_bytes) "
            "VALUES (%s, '00000000-0000-0000-0000-000000000000.jpg', false, 'image/jpeg', 10)",
            (fid,),
        )
    conn.rollback()


def test_photo_storage_key_cannot_be_a_path(conn, user_and_fav):
    _, fid = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO photos (favourite_id, storage_key, exif_stripped, content_type, size_bytes) "
            "VALUES (%s, '../../etc/passwd', true, 'image/jpeg', 10)",
            (fid,),
        )


def test_favourite_must_be_inside_region_without_leaking_coordinates(conn, user_and_fav):
    uid, _ = user_and_fav
    with pytest.raises(psycopg.errors.CheckViolation) as exc:
        conn.execute(
            f"INSERT INTO favourites (owner_id, region, label, geom) VALUES (%s, 'bengaluru', 'X', {MELB})",  # noqa: S608
            (uid,),
        )
    assert "144.96" not in str(exc.value) and "-37.81" not in str(exc.value)


def test_deleting_user_cascades_private_data_but_keeps_audit(conn, user_and_fav):
    uid, fid = user_and_fav
    conn.execute("INSERT INTO audit_log (actor_id, action) VALUES (%s, 'test.event')", (uid,))
    conn.execute("DELETE FROM users WHERE id = %s", (uid,))
    assert conn.execute("SELECT count(*) FROM favourites WHERE id = %s", (fid,)).fetchone()[0] == 0
    orphan = conn.execute("SELECT actor_id FROM audit_log WHERE action = 'test.event'").fetchone()
    assert orphan == (None,)  # evidence retained, person removed
