-- 0006: SYNTHETIC check-ins for the location re-identification experiment (Project 3).
-- Never holds real people's locations. synthetic_user_id is a plain integer with no link
-- to `users`, so it cannot be joined to a real account.

CREATE TABLE checkins_synthetic (
    id                 bigserial PRIMARY KEY,
    synthetic_user_id  integer NOT NULL CHECK (synthetic_user_id > 0),
    region             text NOT NULL REFERENCES regions (code) ON UPDATE CASCADE,
    geom               geometry(Point, 4326) NOT NULL,
    ts                 timestamptz NOT NULL
);
CREATE INDEX checkins_synthetic_ts_idx ON checkins_synthetic (ts);
CREATE INDEX checkins_synthetic_user_idx ON checkins_synthetic (synthetic_user_id);

COMMENT ON TABLE checkins_synthetic IS
    'SYNTHETIC DATA ONLY - generated for the privacy re-identification experiment. Never real people.';
