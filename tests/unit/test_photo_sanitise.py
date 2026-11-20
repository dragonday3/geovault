"""Image sanitising pipeline, tested directly (no database)."""

import io

import pytest
from PIL import Image

from app.services.photos import ImageTooLarge, InvalidImage, PhotoLimits, sanitise
from tests import images

LIMITS = PhotoLimits()


def test_jpeg_gps_and_camera_metadata_removed():
    clean = sanitise(images.jpeg_with_gps(), LIMITS)
    assert clean.content_type == "image/jpeg" and clean.extension == "jpg"
    images.assert_metadata_free(clean.data)


def test_orientation_is_baked_into_pixels_before_exif_is_dropped():
    clean = sanitise(images.jpeg_with_gps(size=(64, 48), orientation=6), LIMITS)
    assert Image.open(io.BytesIO(clean.data)).size == (48, 64)  # rotated, so it still displays upright


def test_png_text_and_xmp_chunks_removed_alpha_kept():
    clean = sanitise(images.png_with_text(), LIMITS)
    img = images.assert_metadata_free(clean.data)
    assert clean.content_type == "image/png" and img.mode == "RGBA"


def test_webp_exif_removed():
    clean = sanitise(images.webp_with_exif(), LIMITS)
    assert clean.content_type == "image/webp"
    images.assert_metadata_free(clean.data)


@pytest.mark.parametrize(
    "data",
    [
        b"just some text pretending to be a photo",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"<html><script>alert(document.cookie)</script></html>",
        b"\xff\xd8\xff\xe0" + b"\x00" * 100,  # JPEG magic bytes, garbage body
        images.jpeg_with_gps()[:200],  # truncated JPEG
        images.gif(),  # real image, unsupported format
        b"",
    ],
)
def test_non_images_and_unsupported_formats_rejected(data):
    with pytest.raises(InvalidImage):
        sanitise(data, LIMITS)


def test_decompression_bomb_rejected_before_decoding():
    bomb = images.decompression_bomb()
    assert len(bomb) < 100_000  # tiny file...
    with pytest.raises(InvalidImage):  # ...100 megapixels: refused from the header alone
        sanitise(bomb, LIMITS)


def test_oversized_input_rejected():
    with pytest.raises(ImageTooLarge):
        sanitise(b"\x00" * (LIMITS.max_bytes + 1), LIMITS)
