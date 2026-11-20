"""Test images carrying the metadata GeoVault must strip."""

import io

from PIL import Image
from PIL.PngImagePlugin import PngInfo

GPS_IFD = 0x8825
MAKE = 0x010F
ORIENTATION = 0x0112
SECRET_MAKE = "SecretCam-9000"
PNG_SECRET = "home address 12 Smith St, Carlton"


def jpeg_with_gps(size=(64, 48), orientation: int | None = 6) -> bytes:
    """JPEG with camera make, GPS position (Melbourne) and an orientation flag."""
    exif = Image.Exif()
    exif[MAKE] = SECRET_MAKE
    if orientation:
        exif[ORIENTATION] = orientation  # 6 = rotate 90 degrees clockwise to display
    exif[GPS_IFD] = {1: "S", 2: (37.0, 48.0, 49.0), 3: "E", 4: (144.0, 57.0, 47.0)}
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, "JPEG", exif=exif)
    data = buf.getvalue()
    # Precondition: the fixture really carries GPS data, so the test cannot pass vacuously.
    assert Image.open(io.BytesIO(data)).getexif().get_ifd(GPS_IFD)
    assert SECRET_MAKE.encode() in data
    return data


def png_with_text() -> bytes:
    info = PngInfo()
    info.add_text("Comment", PNG_SECRET)
    info.add_itxt("XML:com.adobe.xmp", f"<x:xmpmeta>{PNG_SECRET}</x:xmpmeta>")
    buf = io.BytesIO()
    Image.new("RGBA", (32, 32), (0, 120, 200, 128)).save(buf, "PNG", pnginfo=info)
    data = buf.getvalue()
    assert PNG_SECRET.encode() in data
    return data


def webp_with_exif() -> bytes:
    exif = Image.Exif()
    exif[MAKE] = SECRET_MAKE
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 200, 10)).save(buf, "WEBP", exif=exif)
    data = buf.getvalue()
    assert SECRET_MAKE.encode() in data
    return data


def gif() -> bytes:
    buf = io.BytesIO()
    Image.new("P", (8, 8)).save(buf, "GIF")
    return buf.getvalue()


def decompression_bomb() -> bytes:
    """A 10,000 x 10,000 image (100 MP) that compresses to a few KB."""
    buf = io.BytesIO()
    Image.new("1", (10_000, 10_000)).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def assert_metadata_free(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    exif = img.getexif()
    assert len(exif) == 0, dict(exif)
    assert not exif.get_ifd(GPS_IFD)
    for leak in (SECRET_MAKE.encode(), PNG_SECRET.encode(), b"Exif\x00\x00", b"<x:xmpmeta"):
        assert leak not in data
    assert not {"exif", "xmp", "XML:com.adobe.xmp", "Comment", "icc_profile"} & set(img.info)
    return img
