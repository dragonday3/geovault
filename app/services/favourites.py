"""Favourite persistence. Every query that touches a specific favourite filters by BOTH id and
owner_id; owner_id always comes from get_owned_favourite / the authenticated user."""

import uuid

from psycopg import Connection, sql

MAX_FAVOURITES_PER_USER = 1000  # resource-consumption cap (OWASP API4)

OWNER_COLUMNS = """
    id, label, note, region, ST_Y(geom) AS lat, ST_X(geom) AS lon, place_id,
    visibility, share_precision_m, created_at, updated_at
"""


class OutsideRegions(Exception):
    pass


class PlaceNotFound(Exception):
    pass


class TooManyFavourites(Exception):
    pass


def to_owner_out(row: dict) -> dict:
    return {**row, "location": {"lat": row["lat"], "lon": row["lon"]}}


def region_for(conn: Connection, lon: float, lat: float) -> str | None:
    row = conn.execute(
        "SELECT code FROM regions WHERE ST_Intersects(bounds, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
        (lon, lat),
    ).fetchone()
    return row["code"] if row else None


def create(conn: Connection, owner_id: uuid.UUID, data) -> dict:
    count = conn.execute("SELECT count(*) AS n FROM favourites WHERE owner_id = %s", (owner_id,)).fetchone()
    if count["n"] >= MAX_FAVOURITES_PER_USER:
        raise TooManyFavourites

    if data.place_id is not None:
        place = conn.execute(
            "SELECT region, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM places WHERE id = %s",
            (data.place_id,),
        ).fetchone()
        if place is None:
            raise PlaceNotFound
        region, lon, lat = place["region"], place["lon"], place["lat"]
    else:
        lon, lat = data.location.lon, data.location.lat
        region = region_for(conn, lon, lat)
        if region is None:
            raise OutsideRegions

    return conn.execute(
        f"""
        INSERT INTO favourites
            (owner_id, place_id, region, label, note, geom, visibility, share_precision_m)
        VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
        RETURNING {OWNER_COLUMNS}
        """,  # noqa: S608 (OWNER_COLUMNS is a module constant; all values are bound)
        (
            owner_id,
            data.place_id,
            region,
            data.label,
            data.note,
            lon,
            lat,
            data.visibility,
            data.share_precision_m,
        ),
    ).fetchone()


def list_own(conn: Connection, owner_id: uuid.UUID, limit: int, offset: int) -> list[dict]:
    return conn.execute(
        f"""
        SELECT {OWNER_COLUMNS} FROM favourites WHERE owner_id = %s
        ORDER BY created_at DESC, id LIMIT %s OFFSET %s
        """,  # noqa: S608 (constant column list)
        (owner_id, limit, offset),
    ).fetchall()


def get(conn: Connection, favourite_id: uuid.UUID, owner_id: uuid.UUID) -> dict:
    return conn.execute(
        f"SELECT {OWNER_COLUMNS} FROM favourites WHERE id = %s AND owner_id = %s",  # noqa: S608
        (favourite_id, owner_id),
    ).fetchone()


# Allowlist of updatable columns: client field names never become SQL identifiers directly.
_UPDATABLE = ("label", "note", "visibility", "share_precision_m")


def update(conn: Connection, favourite_id: uuid.UUID, owner_id: uuid.UUID, data) -> dict:
    fields = data.model_fields_set
    sets = [
        sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder(col))
        for col in _UPDATABLE
        if col in fields
    ]
    params = {col: getattr(data, col) for col in _UPDATABLE if col in fields}

    if "location" in fields and data.location is not None:
        region = region_for(conn, data.location.lon, data.location.lat)
        if region is None:
            raise OutsideRegions
        sets.append(sql.SQL("geom = ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)"))
        sets.append(sql.SQL("region = %(region)s"))
        sets.append(sql.SQL("place_id = NULL"))  # moved: no longer the linked public place
        params |= {"lon": data.location.lon, "lat": data.location.lat, "region": region}

    sets.append(sql.SQL("updated_at = now()"))
    query = sql.SQL(
        "UPDATE favourites SET {sets} WHERE id = %(id)s AND owner_id = %(owner)s RETURNING {cols}"
    ).format(sets=sql.SQL(", ").join(sets), cols=sql.SQL(OWNER_COLUMNS))
    return conn.execute(query, params | {"id": favourite_id, "owner": owner_id}).fetchone()


def delete(conn: Connection, favourite_id: uuid.UUID, owner_id: uuid.UUID) -> None:
    conn.execute("DELETE FROM favourites WHERE id = %s AND owner_id = %s", (favourite_id, owner_id))


def list_public(conn: Connection, region: str | None, limit: int, offset: int) -> list[dict]:
    """Public favourites. Coordinates are cloaked IN SQL, so exact values never reach Python."""
    return conn.execute(
        """
        SELECT f.label, f.region, f.share_precision_m AS precision_m,
               ST_Y(c.p) AS lat, ST_X(c.p) AS lon,
               o.display_name AS owner_display_name, f.created_at
        FROM favourites f
        JOIN users o ON o.id = f.owner_id AND o.deleted_at IS NULL
        JOIN regions r ON r.code = f.region
        CROSS JOIN LATERAL (SELECT cloak_point(f.geom, r.local_srid, f.share_precision_m) AS p) c
        WHERE f.visibility = 'public' AND (%(region)s::text IS NULL OR f.region = %(region)s)
        ORDER BY f.created_at DESC, f.id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {"region": region, "limit": limit, "offset": offset},
    ).fetchall()
