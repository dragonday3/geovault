"""Download a one-time snapshot of every open dataset in sources.py into data/raw/.

Snapshots are committed, so the app never calls third-party services at runtime and
imports are reproducible. Each file's licence, URL, fetch time and SHA-256 are recorded
in data/raw/MANIFEST.json. Standard library only; run from the repo root:

    py -3.10 data/fetch_sources.py            # all sources
    py -3.10 data/fetch_sources.py osm-bengaluru

This makes a handful of ordinary download requests (one per dataset). It does not
crawl, scan or probe any third-party infrastructure.
"""

import datetime as dt
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import SOURCES  # noqa: E402

RAW = Path(__file__).resolve().parent / "raw"
USER_AGENT = "GeoVault/0.1 (open-data snapshot; +https://github.com/dragonday3/geovault)"
MAX_BYTES = 50 * 1024 * 1024
# Only the tags the adapter needs are kept, keeping snapshots small and free of
# contributor metadata.
OSM_KEEP_TAGS = {
    "name",
    "name:en",
    "amenity",
    "leisure",
    "tourism",
    "historic",
    "railway",
    "station",
    "operator",
    "access",
}


def _get(url: str, data: bytes | None = None) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS source: {url}")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310 (https enforced above)
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"{url} exceeded {MAX_BYTES} bytes")
    return body


def _overpass_to_geojson(raw: bytes) -> dict:
    features = []
    for el in json.loads(raw)["elements"]:
        if "lat" in el:
            lon, lat = el["lon"], el["lat"]
        elif "center" in el:
            lon, lat = el["center"]["lon"], el["center"]["lat"]
        else:
            continue
        props = {k: v for k, v in el.get("tags", {}).items() if k in OSM_KEEP_TAGS}
        props["@id"] = f"{el['type']}/{el['id']}"
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def fetch(key: str, src: dict) -> dict:
    if src["kind"] == "overpass":
        body = _get(src["url"], urllib.parse.urlencode({"data": src["query"]}).encode())
        collection = _overpass_to_geojson(body)
    else:
        collection = json.loads(_get(src["url"]))
    out = RAW / f"{key}.geojson"
    text = json.dumps(collection, ensure_ascii=False, separators=(",", ":"))
    out.write_text(text + "\n", encoding="utf-8")
    return {
        "file": out.name,
        "url": src["url"],
        "publisher": src["publisher"],
        "dataset": src["dataset"],
        "licence": src["licence"],
        "attribution": src["attribution"],
        "region": src["region"],
        "features": len(collection["features"]),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        if hasattr(dt, "UTC")
        else dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),  # noqa: UP017 (py3.10 host)
    }


def main(keys: list[str]) -> None:
    RAW.mkdir(exist_ok=True)
    manifest_path = RAW / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for key in keys or list(SOURCES):
        if key not in SOURCES:
            sys.exit(f"unknown source {key!r}; known: {', '.join(SOURCES)}")
        print(f"fetching {key} ...", flush=True)
        manifest[key] = fetch(key, SOURCES[key])
        print(f"  {manifest[key]['features']} features -> raw/{manifest[key]['file']}")
        time.sleep(2)  # be polite between requests
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
