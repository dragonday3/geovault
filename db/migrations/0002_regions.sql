-- 0002: multi-region support (Melbourne, AU + Bengaluru, IN).
-- Replaces the Victoria-only coordinate fence from 0001 with a per-region bounds check.
-- 0001 is left untouched: applied migrations are immutable.

CREATE TABLE regions (
    code          text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{1,30}$'),
    name          text NOT NULL,
    country_code  char(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
    -- Map view is clamped to these bounds; places must lie inside them.
    bounds        geometry(Polygon, 4326) NOT NULL,
    centre        geometry(Point, 4326) NOT NULL,
    default_zoom  smallint NOT NULL CHECK (default_zoom BETWEEN 3 AND 18),
    -- Minimum zoom keeps the view at city scale. For India this means national and
    -- international boundaries are never rendered (Survey of India depiction rules).
    min_zoom      smallint NOT NULL CHECK (min_zoom BETWEEN 3 AND 18),
    -- Projected CRS (metres) used for location-precision cloaking in this region.
    local_srid    integer NOT NULL CHECK (local_srid > 0),
    CHECK (min_zoom <= default_zoom),
    CHECK (ST_Within(centre, bounds))
);

INSERT INTO regions (code, name, country_code, bounds, centre, default_zoom, min_zoom, local_srid) VALUES
    -- GDA2020 / MGA zone 55
    ('melbourne', 'Melbourne', 'AU',
     ST_MakeEnvelope(144.80, -37.95, 145.10, -37.70, 4326),
     ST_SetSRID(ST_MakePoint(144.9631, -37.8136), 4326), 14, 11, 7855),
    -- WGS 84 / UTM zone 43N
    ('bengaluru', 'Bengaluru', 'IN',
     ST_MakeEnvelope(77.35, 12.75, 77.90, 13.20, 4326),
     ST_SetSRID(ST_MakePoint(77.5946, 12.9716), 4326), 13, 11, 32643);

ALTER TABLE places DROP CONSTRAINT places_geom_in_victoria;
ALTER TABLE places ADD COLUMN region text REFERENCES regions (code) ON UPDATE CASCADE;
UPDATE places SET region = 'melbourne';  -- every pre-0002 row is Melbourne data
ALTER TABLE places ALTER COLUMN region SET NOT NULL;

DROP INDEX places_category_idx;
CREATE INDEX places_region_category_idx ON places (region, category);

-- A CHECK constraint cannot read another table, so a trigger enforces
-- "a place lies inside its region" at the database level, whoever writes the row.
CREATE FUNCTION places_enforce_region_bounds() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM regions r WHERE r.code = NEW.region AND ST_Intersects(r.bounds, NEW.geom)
    ) THEN
        RAISE EXCEPTION 'place % lies outside region %', NEW.source_id, NEW.region
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER places_region_bounds
    BEFORE INSERT OR UPDATE OF geom, region ON places
    FOR EACH ROW EXECUTE FUNCTION places_enforce_region_bounds();
