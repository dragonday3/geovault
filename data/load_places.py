"""Load a GeoJSON file of public places into the `places` table (generic, field-mapped).

For the catalogued open datasets use import_sources.py, which reuses upsert_rows().

Idempotent: upserts on (source, source_id), so re-running an import updates rows
instead of duplicating them. Each feature is validated; bad ones are reported and
skipped, never silently half-loaded.

Run inside the api container (it already has psycopg and GEOVAULT_DATABASE_URL):

    docker compose run --rm -v ./data:/srv/data:ro api \
        python /srv/data/load_places.py /srv/data/samples/melbourne.geojson \
        --region melbourne --source sample
"""

import argparse
import json
import os
import sys

import psycopg

# Non-point geometries (e.g. park polygons) are reduced to a point guaranteed to lie
# inside the shape. ST_PointOnSurface beats ST_Centroid, which can fall outside
# concave parks. The places_region_bounds trigger rejects points outside the region.
UPSERT = """
WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326) AS geom)
INSERT INTO places (region, source, source_id, name, category, geom)
SELECT %(region)s, %(source)s, %(source_id)s, %(name)s, %(category)s,
       CASE WHEN GeometryType(g.geom) = 'POINT' THEN g.geom ELSE ST_PointOnSurface(g.geom) END
FROM g
WHERE ST_IsValid(g.geom) AND NOT ST_IsEmpty(g.geom)
ON CONFLICT (source, source_id) DO UPDATE
   SET region = EXCLUDED.region, name = EXCLUDED.name, category = EXCLUDED.category, geom = EXCLUDED.geom
RETURNING (xmax = 0) AS inserted
"""


def clean(value: object, max_len: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())  # collapse whitespace / newlines
    return text[:max_len] or None


def upsert_rows(conn: psycopg.Connection, region: str, source: str, rows) -> dict:
    """Validate and upsert rows of {source_id, name, category, geometry}.

    Returns counts plus the set of accepted source_ids (used to prune stale rows).
    """
    stats = {"read": 0, "inserted": 0, "updated": 0, "rejected": 0}
    accepted: set[str] = set()
    for i, r in enumerate(rows):
        stats["read"] += 1
        row = {
            "region": region,
            "source": source,
            "source_id": clean(r.get("source_id"), 200),
            "name": clean(r.get("name"), 300),
            "category": clean(r.get("category"), 100),
            "geom": json.dumps(r["geometry"]) if r.get("geometry") else None,
        }
        missing = [k for k, v in row.items() if v is None]
        if missing:
            stats["rejected"] += 1
            print(f"  reject #{i}: missing {missing}", file=sys.stderr)
            continue
        try:
            with conn.transaction():  # savepoint: one bad feature never aborts the load
                res = conn.execute(UPSERT, row).fetchone()
        except psycopg.Error as exc:
            stats["rejected"] += 1
            print(f"  reject #{i} ({row['source_id']}): {exc.diag.message_primary}", file=sys.stderr)
            continue
        if res is None:
            stats["rejected"] += 1
            print(f"  reject #{i} ({row['source_id']}): invalid or empty geometry", file=sys.stderr)
        else:
            stats["inserted" if res[0] else "updated"] += 1
            accepted.add(row["source_id"])
    return {**stats, "accepted_ids": accepted}


def load(
    path: str,
    region: str,
    source: str,
    id_field: str,
    name_field: str,
    category_field: str | None,
    category: str | None,
    dsn: str,
) -> dict[str, int]:
    with open(path, encoding="utf-8") as fh:
        features = json.load(fh).get("features", [])
    rows = (
        {
            "source_id": (f.get("properties") or {}).get(id_field),
            "name": (f.get("properties") or {}).get(name_field),
            "category": (f.get("properties") or {}).get(category_field) if category_field else category,
            "geometry": f.get("geometry"),
        }
        for f in features
    )
    with psycopg.connect(dsn) as conn:
        stats = upsert_rows(conn, region, source, rows)
    stats.pop("accepted_ids")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path")
    ap.add_argument("--region", required=True, help="region code, e.g. melbourne, bengaluru")
    ap.add_argument("--source", required=True, help="dataset identifier stored in places.source")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--name-field", default="name")
    cat = ap.add_mutually_exclusive_group()
    cat.add_argument("--category-field", default="category")
    cat.add_argument("--category", help="constant category for every feature")
    args = ap.parse_args()

    dsn = os.environ.get("GEOVAULT_DATABASE_URL")
    if not dsn:
        sys.exit("GEOVAULT_DATABASE_URL is not set")
    category_field = None if args.category else args.category_field
    stats = load(
        args.path,
        args.region,
        args.source,
        args.id_field,
        args.name_field,
        category_field,
        args.category,
        dsn,
    )
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
