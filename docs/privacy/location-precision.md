# Location precision (cloaking)

A favourite stores the **exact** point privately. Only the owner ever receives it, via
`FavouriteOut` on the owner-only routes. Every other view receives a cloaked location:

| View | Route | Location returned |
|---|---|---|
| Owner | `GET/POST/PATCH /api/favourites[/{id}]` | exact |
| Share link (anyone with the link) | `GET /api/shared/{token}` | cloaked |
| Share recipient | `GET /api/shared/with-me` | cloaked |
| Public list (signed-in users) | `GET /api/favourites/public` | cloaked |

## Method: projected grid snapping

```
cloak_point(geom, region.local_srid, share_precision_m)
  1. project the point into the region's metric CRS
       Melbourne -> EPSG:7855 (GDA2020 / MGA zone 55)
       Bengaluru, Ahmedabad -> EPSG:32643 (WGS 84 / UTM zone 43N)
  2. snap to the CENTRE of its cell_m x cell_m grid square (100 m, 500 m or 1 km)
  3. project back to WGS 84 and round to 6 decimal places
```

The function is defined in SQL (migration `0007_cloaking.sql`) and called inside the queries.
The exact geometry never reaches Python on a non-owner path, and the non-owner response
models (`SharedFavouriteOut`, `PublicFavouriteOut`) have no field that could hold it.

**Guarantee:** the returned point is at most half a cell diagonal from the true point:
71 m at 100 m precision, 354 m at 500 m, and 707 m at 1 km. The tests check this bound at
every precision.

## Why a grid, not random noise

| Approach | Problem |
|---|---|
| Random offset per request | The same location requested N times can be **averaged** back towards the truth |
| Random offset fixed per favourite | Leaks nothing on repeat, but the offset distribution must be documented and hidden. It is harder to reason about. |
| **Deterministic grid snap (chosen)** | Repeated requests return the same point, so there is nothing to average. Simple and verifiable. |

The privacy experiment (`notebooks/reidentification.ipynb`, project 3) compares grid
rounding with k-anonymity cloaking and planar Laplace noise (geo-indistinguishability)
on synthetic data. Its results may revise this choice.

## Other leaks closed

- **Linked public place.** A favourite created from a public place copies that place's
  exact coordinates. Shared views therefore never include `place_id` or the place name,
  which would reveal the exact position.
- **Notes and owner email** are never selected in non-owner queries.
- **Turning a favourite back to `private`** immediately disables every existing share and
  link (the query requires `visibility <> 'private'`).
- **Owner deletion** removes favourites and their shares.

## Residual risks

- **Cell membership.** A cloaked point says the true location lies inside one known cell.
- **Multiple precisions.** Sharing the same place at 1 km and then at 100 m reveals the
  100 m cell. The aligned grid means coarser cells contain finer ones.
- **Several favourites.** Many favourites near the same spot, or a pattern over time, can
  still suggest a home or workplace. This is quantified in the re-identification experiment.
- **The label is free text** chosen by the owner, for example "My house at 12 Smith St".
  It is shared as written.
