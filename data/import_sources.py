"""Import the committed open-data snapshots (data/raw/) into the database.

For each source in sources.py:
  1. verify the snapshot's SHA-256 against raw/MANIFEST.json (detects tampering or
     a half-written download before anything touches the database);
  2. record provenance (licence, attribution, URL, hash) in place_sources;
  3. map features through the source's adapter and upsert them;
  4. prune rows from that source that are no longer in the snapshot.
Each source is one transaction: it either fully imports or leaves the DB unchanged.

Run inside the api container (offline: reads files only, never the network):

    docker compose run --rm -v ./data:/srv/data:ro api python /srv/data/import_sources.py
    ... import_sources.py com-landmarks osm-bengaluru     # selected sources only
    ... import_sources.py --drop-source sample             # remove the hand-made seed rows
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_places import upsert_rows  # noqa: E402
from sources import SOURCES  # noqa: E402

RAW = Path(__file__).resolve().parent / "raw"


def import_source(conn: psycopg.Connection, key: str, meta: dict) -> dict:
    src = SOURCES[key]
    path = RAW / meta["file"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != meta["sha256"]:
        raise RuntimeError(f"{key}: snapshot hash mismatch ({digest} != manifest {meta['sha256']})")

    with conn.transaction():
        conn.execute(
            """
            INSERT INTO place_sources
                (key, region, publisher, dataset, licence, attribution, url, sha256, fetched_at)
            VALUES (%(key)s, %(region)s, %(publisher)s, %(dataset)s, %(licence)s,
                    %(attribution)s, %(url)s, %(sha256)s, %(fetched_at)s)
            ON CONFLICT (key) DO UPDATE SET
                region = EXCLUDED.region, publisher = EXCLUDED.publisher,
                dataset = EXCLUDED.dataset, licence = EXCLUDED.licence,
                attribution = EXCLUDED.attribution, url = EXCLUDED.url,
                sha256 = EXCLUDED.sha256, fetched_at = EXCLUDED.fetched_at, imported_at = now()
            """,
            {
                "key": key,
                **{
                    k: meta[k]
                    for k in (
                        "region",
                        "publisher",
                        "dataset",
                        "licence",
                        "attribution",
                        "url",
                        "sha256",
                        "fetched_at",
                    )
                },
            },
        )

        features = json.loads(path.read_text(encoding="utf-8"))["features"]
        skipped = 0
        rows = []
        for f in features:
            mapped = src["adapter"](f)
            if mapped is None:
                skipped += 1
                continue
            source_id, name, category = mapped
            rows.append(
                {"source_id": source_id, "name": name, "category": category, "geometry": f.get("geometry")}
            )

        stats = upsert_rows(conn, src["region"], key, rows)
        accepted = stats.pop("accepted_ids")
        pruned = conn.execute(
            "DELETE FROM places WHERE source = %s AND NOT (source_id = ANY(%s))",
            (key, list(accepted)),
        ).rowcount
    return {**stats, "skipped_by_adapter": skipped, "pruned": pruned}


def main() -> None:
    ap = argparse.ArgumentParser(description="Import committed open-data snapshots.")
    ap.add_argument("keys", nargs="*", help=f"sources to import (default: all): {', '.join(SOURCES)}")
    ap.add_argument(
        "--drop-source",
        action="append",
        default=[],
        help="delete all places from this source key (e.g. sample)",
    )
    args = ap.parse_args()

    dsn = os.environ.get("GEOVAULT_DATABASE_URL")
    if not dsn:
        sys.exit("GEOVAULT_DATABASE_URL is not set")
    manifest = json.loads((RAW / "MANIFEST.json").read_text())
    keys = args.keys or [k for k in SOURCES if k in manifest]
    unknown = [k for k in keys if k not in SOURCES or k not in manifest]
    if unknown:
        sys.exit(f"not in sources.py and MANIFEST.json: {unknown}")

    with psycopg.connect(dsn) as conn:
        for key in args.drop_source:
            n = conn.execute("DELETE FROM places WHERE source = %s", (key,)).rowcount
            print(json.dumps({"dropped_source": key, "rows": n}))
        conn.commit()
        for key in keys:
            print(json.dumps({"source": key, **import_source(conn, key, manifest[key])}), flush=True)


if __name__ == "__main__":
    main()
