-- 0005: private favourites, sharing and photos (API arrives in milestones 7-8).
-- Constraints here are the last line of defence if application code is wrong.

CREATE TYPE favourite_visibility AS ENUM ('private', 'shared', 'public');

CREATE TABLE favourites (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    place_id           bigint REFERENCES places (id) ON DELETE SET NULL,
    region             text NOT NULL REFERENCES regions (code) ON UPDATE CASCADE,
    label              text NOT NULL CHECK (length(label) BETWEEN 1 AND 100),
    note               text CHECK (length(note) <= 2000),           -- private, owner-only
    geom               geometry(Point, 4326) NOT NULL,              -- exact, owner-only
    visibility         favourite_visibility NOT NULL DEFAULT 'private',
    share_precision_m  integer NOT NULL DEFAULT 100 CHECK (share_precision_m IN (100, 500, 1000)),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX favourites_owner_idx ON favourites (owner_id);
CREATE INDEX favourites_geom_gix ON favourites USING gist (geom);

-- Favourites must lie inside their region (its projected CRS is used for cloaking).
-- Unlike the places trigger, the error never echoes the coordinates.
CREATE FUNCTION favourites_enforce_region_bounds() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM regions r WHERE r.code = NEW.region AND ST_Intersects(r.bounds, NEW.geom)
    ) THEN
        RAISE EXCEPTION 'favourite lies outside region %', NEW.region
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER favourites_region_bounds
    BEFORE INSERT OR UPDATE OF geom, region ON favourites
    FOR EACH ROW EXECUTE FUNCTION favourites_enforce_region_bounds();

-- A share is EITHER with a registered user OR an expiring link, never both or neither.
-- Link tokens are stored only as SHA-256 digests.
CREATE TABLE shares (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    favourite_id         uuid NOT NULL REFERENCES favourites (id) ON DELETE CASCADE,
    shared_with_user_id  uuid REFERENCES users (id) ON DELETE CASCADE,
    share_token_hash     bytea UNIQUE CHECK (octet_length(share_token_hash) = 32),
    expires_at           timestamptz,
    revoked_at           timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT shares_exactly_one_target CHECK (num_nonnulls(shared_with_user_id, share_token_hash) = 1),
    CONSTRAINT shares_links_expire CHECK (share_token_hash IS NULL OR expires_at IS NOT NULL),
    CONSTRAINT shares_expiry_in_future CHECK (expires_at IS NULL OR expires_at > created_at)
);
CREATE INDEX shares_favourite_idx ON shares (favourite_id);
-- One active user-share per (favourite, recipient).
CREATE UNIQUE INDEX shares_active_user_uk ON shares (favourite_id, shared_with_user_id)
    WHERE shared_with_user_id IS NOT NULL AND revoked_at IS NULL;

-- Photo metadata. The DB refuses any record whose file was not EXIF-stripped, and storage
-- keys are server-generated UUIDs (no user-controlled paths).
CREATE TABLE photos (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    favourite_id   uuid NOT NULL REFERENCES favourites (id) ON DELETE CASCADE,
    storage_key    text NOT NULL UNIQUE
                   CHECK (storage_key ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png|webp)$'),
    exif_stripped  boolean NOT NULL CHECK (exif_stripped),
    content_type   text NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    size_bytes     integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX photos_favourite_idx ON photos (favourite_id);
