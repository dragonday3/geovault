"""Explicit response models for the public places API (GeoJSON-shaped)."""

from typing import Literal

from pydantic import BaseModel


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [lon, lat], GeoJSON order


class PlaceProperties(BaseModel):
    name: str
    category: str
    region: str
    source: str
    distance_m: float | None = None  # only set by /near


class PlaceFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: PointGeometry
    properties: PlaceProperties


class PlaceCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PlaceFeature]


class CategoryCount(BaseModel):
    category: str
    count: int


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "unavailable"]


class Region(BaseModel):
    code: str
    name: str
    country_code: str
    bbox: tuple[float, float, float, float]  # minLon, minLat, maxLon, maxLat
    centre: tuple[float, float]  # lon, lat
    default_zoom: int
    min_zoom: int
