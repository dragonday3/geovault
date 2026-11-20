-- 0010: the ONLY relation GeoServer may read.
-- A view over the public open-data table, owned by the app role. geoserver_ro gets SELECT on
-- this view and nothing else, so WMS/WFS can never reach private tables, whatever GeoServer
-- itself is configured (or misconfigured) to publish.

CREATE VIEW public_places AS
SELECT id, name, category, region, source, geom
FROM places;

COMMENT ON VIEW public_places IS
    'Public open data only (City of Melbourne, OpenStreetMap). The sole relation readable by geoserver_ro.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoserver_ro') THEN
        GRANT SELECT ON public_places TO geoserver_ro;
    END IF;
END
$$;
