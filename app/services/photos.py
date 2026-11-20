"""Photo upload processing and storage.

Pipeline (every upload, no exceptions):
  1. size cap      - enforced before parsing by UploadGuard, and again on the bytes here
  2. decode        - Pillow identifies the REAL format from the content (the client's filename
                     and Content-Type are ignored); only JPEG, PNG and WebP are accepted
  3. bomb check    - pixel count from the header is checked BEFORE decoding pixels
  4. orientation   - the EXIF rotation is applied to the pixels, so the photo still displays
                     upright once EXIF is gone
  5. rebuild       - pixels are copied into a brand-new image. Nothing from the original
                     container survives: EXIF (incl. GPS), XMP, ICC, PNG text chunks, comments
  6. re-encode     - saved in the same format
  7. store         - under a random UUID key; client filenames never touch the filesystem
"""

import io
import logging
import os
import re
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg import Connection

log = logging.getLogger("geovault.photos")

# format -> (content type, extension, save options)
_FORMATS = {
    "JPEG": ("image/jpeg", "jpg", {"quality": 85, "optimize": True}),
    "PNG": ("image/png", "png", {"optimize": True}),
    "WEBP": ("image/webp", "webp", {"quality": 85}),
}
_KEY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png|webp)$")


@dataclass(frozen=True)
class PhotoLimits:
    max_bytes: int = 5 * 1024 * 1024  # 5 MiB, also enforced by a DB CHECK
    max_pixels: int = 40_000_000  # ~40 MP: real photos fit, decompression bombs do not


class InvalidImage(Exception):
    pass


class ImageTooLarge(Exception):
    pass


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    content_type: str
    extension: str


def sanitise(data: bytes, limits: PhotoLimits) -> CleanImage:
    if len(data) > limits.max_bytes:
        raise ImageTooLarge
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:  # reads the header only
                fmt = probe.format
                if fmt not in _FORMATS:
                    raise InvalidImage(f"unsupported format {fmt}")
                if probe.width * probe.height > limits.max_pixels:
                    raise InvalidImage("image dimensions too large")
                probe.verify()  # structural integrity check (truncation, corruption)
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                img = ImageOps.exif_transpose(img)
                has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
                mode = "RGBA" if has_alpha and fmt != "JPEG" else ("L" if img.mode == "L" else "RGB")
                pixels = img.convert(mode)
                clean = Image.frombytes(mode, pixels.size, pixels.tobytes())  # no metadata at all
    except InvalidImage:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise InvalidImage(type(exc).__name__) from None

    content_type, ext, options = _FORMATS[fmt]
    out = io.BytesIO()
    clean.save(out, format=fmt, **options)
    encoded = out.getvalue()
    if len(encoded) > limits.max_bytes:
        raise ImageTooLarge
    return CleanImage(encoded, content_type, ext)


class LocalPhotoStore:
    """Files under one directory, named only by server-generated keys.
    # ponytail: local disk; an S3 store with the same three methods replaces it in AWS (week 5).
    """

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):  # defence in depth: keys are ours, but never trust a path
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("storage key escapes the photo directory")
        return path

    def put(self, key: str, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)  # atomic: readers never see a half-written file

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError:
            log.warning("photo file could not be deleted")  # never log the key with user context


def attach(conn: Connection, store: LocalPhotoStore, favourite_id: uuid.UUID, image: CleanImage) -> dict:
    """Store the photo and (re)place the favourite's photo row. Returns the new row."""
    key = f"{uuid.uuid4()}.{image.extension}"
    store.put(key, image.data)
    old = conn.execute(
        "DELETE FROM photos WHERE favourite_id = %s RETURNING storage_key", (favourite_id,)
    ).fetchone()
    row = conn.execute(
        """
        INSERT INTO photos (favourite_id, storage_key, exif_stripped, content_type, size_bytes)
        VALUES (%s, %s, true, %s, %s)
        RETURNING id, content_type, size_bytes, created_at
        """,
        (favourite_id, key, image.content_type, len(image.data)),
    ).fetchone()
    if old:
        store.delete(old["storage_key"])
    return row


def for_favourite(conn: Connection, favourite_id: uuid.UUID) -> dict | None:
    return conn.execute(
        "SELECT storage_key, content_type FROM photos WHERE favourite_id = %s", (favourite_id,)
    ).fetchone()


def keys_for_favourite(conn: Connection, favourite_id: uuid.UUID) -> list[str]:
    return [
        r["storage_key"]
        for r in conn.execute("SELECT storage_key FROM photos WHERE favourite_id = %s", (favourite_id,))
    ]


def keys_for_owner(conn: Connection, owner_id: uuid.UUID) -> list[str]:
    return [
        r["storage_key"]
        for r in conn.execute(
            "SELECT p.storage_key FROM photos p JOIN favourites f ON f.id = p.favourite_id "
            "WHERE f.owner_id = %s",
            (owner_id,),
        )
    ]


def delete_files(store: LocalPhotoStore, keys: list[str]) -> None:
    for key in keys:
        store.delete(key)
