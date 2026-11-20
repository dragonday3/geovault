# Photo handling

Phone photos usually carry EXIF metadata. That metadata often includes **GPS coordinates
precise to a few metres**, the device make and model, and timestamps. A photo of a "private"
favourite would otherwise publish its exact location, bypassing location cloaking. Every
upload is therefore rebuilt from pixels before it is stored.

## Pipeline

| Step | Control | Threat addressed |
|---|---|---|
| 1 | `UploadGuard` middleware: `Content-Length` required (411) and ≤ 5 MB + multipart overhead (413), checked **before** the body is parsed; bytes received are counted too | Disk/memory exhaustion (API4). FastAPI would otherwise spool the whole body first |
| 2 | Pillow decodes the content. Only JPEG, PNG and WebP are accepted. The client's filename and `Content-Type` are ignored | SVG/HTML-with-script uploads (stored XSS), polyglots, format confusion |
| 3 | Pixel count read from the header and refused above 40 MP **before** decoding pixels; `DecompressionBombWarning` treated as an error | Decompression bombs (a few KB → GBs of RAM) |
| 4 | `verify()` + full decode | Truncated or corrupt files |
| 5 | EXIF orientation applied to the pixels (`exif_transpose`) | Photos turning sideways once EXIF is gone |
| 6 | Pixels copied into a **brand-new image** (`Image.frombytes`) | Drops EXIF (incl. GPS), XMP, ICC, PNG text/iTXt chunks and comments as a class, not by tag list |
| 7 | Re-encoded in the same format; output size re-checked | Re-encoding cannot bypass the cap |
| 8 | Stored as `<uuid4>.<ext>` in a dedicated directory. Key format re-validated and path containment checked on every access. Atomic write | Path traversal, overwrites, guessable names |
| 9 | DB `CHECK (exif_stripped)`, a storage-key regex, an allowed content-type list, a size range, and one photo per favourite | Defence in depth if app code regresses |

## Delivery

Photos are served only through authorization-checked routes:

| Who | Route | Rule |
|---|---|---|
| Owner | `GET /api/favourites/{id}/photo` | `get_owned_favourite` (others get 404) |
| Link holder | `GET /api/shared/{token}/photo` | same validity as the link view: not revoked or expired, favourite not private |
| Recipient | `GET /api/shared/with-me/{share_id}/photo` | only the recipient of that share |

Response headers:
- `Content-Type` comes from the DB row, which was set from the decoded format.
- `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'; sandbox` mean the bytes are only ever treated as an image.
- `Content-Disposition: inline`.
- `Cache-Control: private, no-store`.
- `Referrer-Policy: no-referrer` on link routes.

## Lifecycle

- **Replacing a photo** deletes the old file.
- **Deleting a photo, a favourite or the whole account** deletes the files, not just the rows. The DB cascade alone would leave orphaned files on disk.

## Verification

- `tests/images.py` builds fixtures that **demonstrably contain** the metadata: GPS IFD, camera make, orientation, PNG text and XMP, WebP EXIF.
- Tests assert the fixtures carry it first, then assert the **downloaded** bytes contain none of it.
- Mutation-tested: keeping the original metadata, or removing the upload guard, makes the suite fail.

## Residual risks

- **Image content itself** (a recognisable street or house number) can reveal a location.
  Metadata stripping cannot address that. Users are shown that photos are visible to share
  recipients.
- **Upload buffering.** A request that lies about `Content-Length` is cut off once it exceeds
  the declared size, but it is still buffered up to the cap in the size-limited `/tmp`
  (64 MB tmpfs). In AWS a reverse proxy enforces a request-body limit as well.
- **Local disk storage.** It is replaced by a private, encrypted S3 bucket in the cloud
  deployment (project 2).
