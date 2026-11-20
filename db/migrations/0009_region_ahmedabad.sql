-- 0009: add Ahmedabad (Gujarat, IN). Same rules as Bengaluru: the map is clamped to the city
-- at minimum zoom 11, so national boundaries never render.
INSERT INTO regions (code, name, country_code, bounds, centre, default_zoom, min_zoom, local_srid) VALUES
    -- WGS 84 / UTM zone 43N (72-78 E) covers Ahmedabad (~72.57 E)
    ('ahmedabad', 'Ahmedabad', 'IN',
     ST_MakeEnvelope(72.40, 22.90, 72.75, 23.20, 4326),
     ST_SetSRID(ST_MakePoint(72.5714, 23.0225), 4326), 13, 11, 32643);
