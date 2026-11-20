-- 0001: public places dataset (City of Melbourne open data + sample seed).
-- Public data only. Private/user-owned tables arrive in later migrations.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE places (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL CHECK (length(name) BETWEEN 1 AND 300),
    category    text NOT NULL CHECK (length(category) BETWEEN 1 AND 100),
    source      text NOT NULL CHECK (length(source) BETWEEN 1 AND 100),
    source_id   text NOT NULL CHECK (length(source_id) BETWEEN 1 AND 200),
    geom        geometry(Point, 4326) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- Loader upserts on this key, so re-running an import never duplicates rows.
    CONSTRAINT places_source_uk UNIQUE (source, source_id),
    -- Sanity fence: Victoria's bounding box. Rejects swapped lat/lon and junk coordinates.
    CONSTRAINT places_geom_in_victoria CHECK (
        ST_X(geom) BETWEEN 140.9 AND 150.0 AND ST_Y(geom) BETWEEN -39.2 AND -33.9
    )
);

-- bbox queries (&& operator) use the geometry index;
-- metre-accurate radius queries use the geography expression index.
CREATE INDEX places_geom_gix ON places USING gist (geom);
CREATE INDEX places_geog_gix ON places USING gist ((geom::geography));
CREATE INDEX places_category_idx ON places (category);
