"""Photo API: upload limits, EXIF/GPS stripping end to end, safe delivery, access control,
and file cleanup. LAB-01 (photos) and LAB-04 (upload size) lab variants will remove controls
proven here."""

import pytest

from tests import images
from tests.helpers import PASSWORD, make_user

MELB = {"lat": -37.8136, "lon": 144.9631}


def fav(client, user, visibility="shared"):
    r = client.post(
        "/api/favourites",
        json={"label": "Spot", "location": MELB, "visibility": visibility, "share_precision_m": 500},
        headers=user["headers"],
    )
    return r.json()


def upload(client, user, fav_id, data, name="photo.jpg", ctype="image/jpeg"):
    return client.post(
        f"/api/favourites/{fav_id}/photo", files={"file": (name, data, ctype)}, headers=user["headers"]
    )


def stored_files(client) -> set[str]:
    root = client.app.state.photo_store.root
    return {p.name for p in root.iterdir()} if root.exists() else set()


# --- upload + stripping ------------------------------------------------------------------------


def test_upload_strips_gps_end_to_end(client):
    u = make_user(client)
    f = fav(client, u)
    r = upload(client, u, f["id"], images.jpeg_with_gps())
    assert r.status_code == 201, r.text
    assert set(r.json()) == {"content_type", "size_bytes", "created_at"}  # no storage key exposed

    got = client.get(f"/api/favourites/{f['id']}/photo", headers=u["headers"])
    assert got.status_code == 200
    images.assert_metadata_free(got.content)
    assert client.get(f"/api/favourites/{f['id']}", headers=u["headers"]).json()["has_photo"] is True


def test_photo_rows_record_stripping(client, conn):
    u = make_user(client)
    f = fav(client, u)
    upload(client, u, f["id"], images.png_with_text(), name="x.png", ctype="image/png")
    row = conn.execute(
        "SELECT exif_stripped, content_type, storage_key FROM photos WHERE favourite_id = %s", (f["id"],)
    ).fetchone()
    assert row[0] is True and row[1] == "image/png"
    assert row[2] in stored_files(client)


def test_safe_delivery_headers(client):
    u = make_user(client)
    f = fav(client, u)
    upload(client, u, f["id"], images.jpeg_with_gps())
    r = client.get(f"/api/favourites/{f['id']}/photo", headers=u["headers"])
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["content-disposition"].startswith("inline")
    assert "no-store" in r.headers["cache-control"]


def test_declared_content_type_and_filename_are_ignored(client):
    u = make_user(client)
    f = fav(client, u)
    before = stored_files(client)
    r = upload(client, u, f["id"], images.png_with_text(), name="../../../etc/passwd.jpg", ctype="image/jpeg")
    assert r.status_code == 201
    assert r.json()["content_type"] == "image/png"  # decided by decoding, not by the client
    new = stored_files(client) - before
    assert len(new) == 1 and "passwd" not in next(iter(new)) and next(iter(new)).endswith(".png")


@pytest.mark.parametrize(
    "data, name, ctype",
    [
        (
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            "a.svg",
            "image/svg+xml",
        ),
        (b"<html><script>alert(1)</script></html>", "a.jpg", "image/jpeg"),
        (images.gif(), "a.gif", "image/gif"),
        (images.decompression_bomb(), "bomb.png", "image/png"),
    ],
)
def test_rejects_non_images_and_bombs(client, conn, data, name, ctype):
    u = make_user(client)
    f = fav(client, u)
    r = upload(client, u, f["id"], data, name, ctype)
    assert r.status_code == 422
    rejected = conn.execute(
        "SELECT count(*) FROM audit_log WHERE action = 'photo.upload_rejected' AND target_id = %s", (f["id"],)
    ).fetchone()[0]
    assert rejected == 1


def test_oversized_upload_rejected_before_parsing(client):
    u = make_user(client)
    f = fav(client, u)
    r = upload(client, u, f["id"], b"\xff" * (6 * 1024 * 1024))
    assert r.status_code == 413


def test_upload_without_content_length_is_refused(client):
    u = make_user(client)
    f = fav(client, u)

    def chunks():  # chunked transfer encoding: no Content-Length
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.jpg"\r\n\r\n'
        yield images.jpeg_with_gps()
        yield b"\r\n--b--\r\n"

    r = client.post(
        f"/api/favourites/{f['id']}/photo",
        content=chunks(),
        headers=u["headers"] | {"content-type": "multipart/form-data; boundary=b"},
    )
    assert r.status_code == 411


def test_reupload_replaces_and_deletes_old_file(client, conn):
    u = make_user(client)
    f = fav(client, u)
    upload(client, u, f["id"], images.jpeg_with_gps())
    first = conn.execute("SELECT storage_key FROM photos WHERE favourite_id = %s", (f["id"],)).fetchone()[0]
    upload(client, u, f["id"], images.webp_with_exif(), name="b.webp", ctype="image/webp")
    keys = [r[0] for r in conn.execute("SELECT storage_key FROM photos WHERE favourite_id = %s", (f["id"],))]
    assert len(keys) == 1 and keys[0] != first
    assert first not in stored_files(client) and keys[0] in stored_files(client)


# --- access control ----------------------------------------------------------------------------


def test_other_users_cannot_touch_photo(client):
    owner, mallory = make_user(client), make_user(client)
    f = fav(client, owner)
    upload(client, owner, f["id"], images.jpeg_with_gps())
    original = client.get(f"/api/favourites/{f['id']}/photo", headers=owner["headers"]).content

    assert client.get(f"/api/favourites/{f['id']}/photo", headers=mallory["headers"]).status_code == 404
    assert (
        upload(client, mallory, f["id"], images.webp_with_exif(), "x.webp", "image/webp").status_code == 404
    )
    assert client.delete(f"/api/favourites/{f['id']}/photo", headers=mallory["headers"]).status_code == 404
    assert client.get(f"/api/favourites/{f['id']}/photo", headers=owner["headers"]).content == original


def test_photo_routes_require_authentication(client):
    owner = make_user(client)
    f = fav(client, owner)
    assert client.get(f"/api/favourites/{f['id']}/photo").status_code == 401


def test_link_share_photo(client):
    owner = make_user(client)
    f = fav(client, owner)
    upload(client, owner, f["id"], images.jpeg_with_gps())
    share = client.post(
        f"/api/favourites/{f['id']}/share", json={"type": "link"}, headers=owner["headers"]
    ).json()

    assert client.get(share["path"]).json()["has_photo"] is True
    r = client.get(share["path"] + "/photo")  # anonymous
    assert r.status_code == 200 and r.headers["referrer-policy"] == "no-referrer"
    images.assert_metadata_free(r.content)

    client.delete(f"/api/favourites/{f['id']}/shares/{share['id']}", headers=owner["headers"])
    assert client.get(share["path"] + "/photo").status_code == 404


def test_private_favourite_photo_not_reachable_via_old_link(client):
    owner = make_user(client)
    f = fav(client, owner)
    upload(client, owner, f["id"], images.jpeg_with_gps())
    share = client.post(
        f"/api/favourites/{f['id']}/share", json={"type": "link"}, headers=owner["headers"]
    ).json()
    client.patch(f"/api/favourites/{f['id']}", json={"visibility": "private"}, headers=owner["headers"])
    assert client.get(share["path"] + "/photo").status_code == 404


def test_recipient_photo_access_is_scoped_to_their_share(client):
    owner, friend, stranger = make_user(client), make_user(client), make_user(client)
    f = fav(client, owner)
    upload(client, owner, f["id"], images.jpeg_with_gps())
    share = client.post(
        f"/api/favourites/{f['id']}/share",
        json={"type": "user", "email": friend["email"]},
        headers=owner["headers"],
    ).json()
    path = f"/api/shared/with-me/{share['id']}/photo"
    assert client.get(path, headers=friend["headers"]).status_code == 200
    assert client.get(path, headers=stranger["headers"]).status_code == 404


# --- cleanup -----------------------------------------------------------------------------------


def test_deleting_favourite_removes_file(client, conn):
    u = make_user(client)
    f = fav(client, u)
    upload(client, u, f["id"], images.jpeg_with_gps())
    key = conn.execute("SELECT storage_key FROM photos WHERE favourite_id = %s", (f["id"],)).fetchone()[0]
    client.delete(f"/api/favourites/{f['id']}", headers=u["headers"])
    assert key not in stored_files(client)


def test_deleting_account_removes_files(client, conn):
    u = make_user(client)
    f = fav(client, u)
    upload(client, u, f["id"], images.jpeg_with_gps())
    key = conn.execute("SELECT storage_key FROM photos WHERE favourite_id = %s", (f["id"],)).fetchone()[0]
    client.request("DELETE", "/api/users/me", json={"password": PASSWORD}, headers=u["headers"])
    assert key not in stored_files(client)


def test_delete_photo(client):
    u = make_user(client)
    f = fav(client, u)
    upload(client, u, f["id"], images.jpeg_with_gps())
    assert client.delete(f"/api/favourites/{f['id']}/photo", headers=u["headers"]).status_code == 204
    assert client.get(f"/api/favourites/{f['id']}/photo", headers=u["headers"]).status_code == 404
