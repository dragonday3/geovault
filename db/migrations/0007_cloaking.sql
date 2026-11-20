-- 0007: location precision cloaking for shared and public views.
--
-- cloak_point(g, srid, cell_m) returns the CENTRE of the cell_m x cell_m grid square that
-- contains g, computed in a metric projected CRS (the region's local_srid: MGA 55 for
-- Melbourne, UTM 43N for Bengaluru) so that cells are true metres, not distorted degrees.
--
-- Why a fixed grid rather than random noise: snapping is deterministic, so requesting the
-- same shared favourite many times always yields the same point. Fresh random noise per
-- request could be averaged back towards the true location.
-- Residual risk (documented): a point near a cell edge is still known to lie in that cell,
-- and an owner who shares the same place at several precisions narrows it to the
-- intersection of the cells (which, with an aligned grid, is just the finest cell).

CREATE FUNCTION cloak_point(g geometry, srid integer, cell_m integer)
RETURNS geometry
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$
    SELECT ST_Transform(
               ST_SetSRID(
                   ST_MakePoint(
                       floor(ST_X(p) / cell_m) * cell_m + cell_m / 2.0,
                       floor(ST_Y(p) / cell_m) * cell_m + cell_m / 2.0
                   ),
                   srid
               ),
               4326
           )
    FROM (SELECT ST_Transform(g, srid) AS p) projected
$$;

COMMENT ON FUNCTION cloak_point(geometry, integer, integer) IS
    'Snap a point to the centre of its cell_m metre grid cell in projected CRS srid. Used for every non-owner view of a favourite.';
