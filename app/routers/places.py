"""Public places API. Read-only, unauthenticated, public open data only.

Every query is a static string literal with bound parameters (no f-strings, so
ruff's S608 SQL-injection rule stays silent on secure code). Optional filters use the
`(%(x)s IS NULL OR col = %(x)s)` pattern instead of string-building, so there is
no code path where request input becomes SQL text.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.database import get_conn
from app.schemas.places import CategoryCount, DataSource, PlaceCollection, PlaceFeature, Region

router = APIRouter(prefix="/api", tags=["places"])

Conn = Annotated[Connection, Depends(get_conn)]

# Resource-consumption caps (OWASP API4). Lab mode will deliberately remove these.
MAX_RADIUS_M = 5000
MAX_NEAR_LIMIT = 100
MAX_LIST_LIMIT = 500

RegionCode = Annotated[
    str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,30}$", description="e.g. melbourne, bengaluru")
]


def _feature(row: dict) -> PlaceFeature:
    return PlaceFeature(
        id=row["id"],
        geometry={"coordinates": (row["lon"], row["lat"])},
        properties={
            "name": row["name"],
            "category": row["category"],
            "region": row["region"],
            "source": row["source"],
            "distance_m": row.get("distance_m"),
        },
    )


def _parse_bbox(raw: str) -> tuple[float, float, float, float]:
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in raw.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be minLon,minLat,maxLon,maxLat") from None
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise HTTPException(422, "bbox out of range or inverted")
    return min_lon, min_lat, max_lon, max_lat


def _like_pattern(q: str) -> str:
    # Escape LIKE wildcards so user text is matched literally.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/regions", response_model=list[Region])
def regions(conn: Conn):
    return conn.execute(
        """
        SELECT code, name, country_code,
               ARRAY[ST_XMin(bounds), ST_YMin(bounds), ST_XMax(bounds), ST_YMax(bounds)] AS bbox,
               ARRAY[ST_X(centre), ST_Y(centre)] AS centre,
               default_zoom, min_zoom
        FROM regions ORDER BY name
        """
    ).fetchall()


@router.get("/sources", response_model=list[DataSource])
def sources(conn: Conn, region: RegionCode = None):
    """Provenance and licence attribution for every imported dataset."""
    return conn.execute(
        """
        SELECT key, region, publisher, dataset, licence, attribution, url, fetched_at
        FROM place_sources
        WHERE (%(region)s::text IS NULL OR region = %(region)s)
        ORDER BY region, key
        """,
        {"region": region},
    ).fetchall()


@router.get("/categories", response_model=list[CategoryCount])
def categories(conn: Conn, region: RegionCode = None):
    return conn.execute(
        """
        SELECT category, count(*) AS count FROM places
        WHERE (%(region)s::text IS NULL OR region = %(region)s)
        GROUP BY category ORDER BY category
        """,
        {"region": region},
    ).fetchall()


@router.get("/places", response_model=PlaceCollection)
def list_places(
    conn: Conn,
    region: RegionCode = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    bbox: Annotated[str | None, Query(max_length=100, description="minLon,minLat,maxLon,maxLat")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = 200,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    box = _parse_bbox(bbox) if bbox else (None, None, None, None)
    rows = conn.execute(
        """
        SELECT id, name, category, region, source, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM places
        WHERE (%(region)s::text IS NULL OR region = %(region)s)
          AND (%(cat)s::text IS NULL OR category = %(cat)s)
          AND (%(q)s::text IS NULL OR name ILIKE %(q)s)
          AND (%(x1)s::float8 IS NULL
               OR geom && ST_MakeEnvelope(%(x1)s, %(y1)s, %(x2)s, %(y2)s, 4326))
        ORDER BY name, id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            "region": region,
            "cat": category,
            "q": _like_pattern(q) if q else None,
            "x1": box[0],
            "y1": box[1],
            "x2": box[2],
            "y2": box[3],
            "limit": limit,
            "offset": offset,
        },
    ).fetchall()
    return PlaceCollection(features=[_feature(r) for r in rows])


@router.get("/places/near", response_model=PlaceCollection)
def places_near(
    conn: Conn,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[int, Query(ge=1, le=MAX_RADIUS_M)] = 1000,
    limit: Annotated[int, Query(ge=1, le=MAX_NEAR_LIMIT)] = 20,
    category: Annotated[str | None, Query(max_length=100)] = None,
    region: RegionCode = None,
):
    rows = conn.execute(
        """
        WITH p AS (SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS g)
        SELECT id, name, category, region, source, ST_X(geom) AS lon, ST_Y(geom) AS lat,
               ST_Distance(geom::geography, p.g) AS distance_m
        FROM places, p
        WHERE ST_DWithin(geom::geography, p.g, %(r)s)
          AND (%(cat)s::text IS NULL OR category = %(cat)s)
          AND (%(region)s::text IS NULL OR region = %(region)s)
        ORDER BY distance_m, id
        LIMIT %(limit)s
        """,
        {"lat": lat, "lon": lon, "r": radius_m, "cat": category, "region": region, "limit": limit},
    ).fetchall()
    return PlaceCollection(features=[_feature(r) for r in rows])


@router.get("/places/{place_id}", response_model=PlaceFeature)
def get_place(conn: Conn, place_id: int):
    row = conn.execute(
        "SELECT id, name, category, region, source, ST_X(geom) AS lon, ST_Y(geom) AS lat"
        " FROM places WHERE id = %s",
        (place_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Place not found")
    return _feature(row)
