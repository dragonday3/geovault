-- 0003: provenance for imported open datasets.
-- CC BY 4.0 and ODbL both require attribution, so licence and attribution text are stored
-- with the data and served by GET /api/sources for display on the map.

CREATE TABLE place_sources (
    key          text PRIMARY KEY CHECK (key ~ '^[a-z0-9][a-z0-9-]{1,60}$'),
    region       text NOT NULL REFERENCES regions (code) ON UPDATE CASCADE,
    publisher    text NOT NULL CHECK (length(publisher) BETWEEN 1 AND 200),
    dataset      text NOT NULL CHECK (length(dataset) BETWEEN 1 AND 300),
    licence      text NOT NULL CHECK (length(licence) BETWEEN 1 AND 100),
    attribution  text NOT NULL CHECK (length(attribution) BETWEEN 1 AND 500),
    url          text NOT NULL CHECK (url ~ '^https://'),
    sha256       char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    fetched_at   timestamptz NOT NULL,
    imported_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX place_sources_region_idx ON place_sources (region);
