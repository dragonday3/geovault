"""Favourite and share models.

Two strictly separate output shapes:
  * FavouriteOut       - owner only: exact coordinates and the private note.
  * Shared/Public outs - everyone else: a CloakedLocation and nothing private. These models
    have NO field that could carry exact coordinates, the note, the owner's email or the
    linked place, so leaking them would be a type error, not a code-review miss.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Visibility = Literal["private", "shared", "public"]
Precision = Literal[100, 500, 1000]

_CONTROL = {chr(c) for c in range(32)} - {"\n", "\t"}


def _clean_label(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("Label must not be blank.")
    return v


def _clean_note(v: str | None) -> str | None:
    if v is None:
        return None
    if any(ch in _CONTROL for ch in v):
        raise ValueError("Note contains control characters.")
    return v.strip() or None


class LatLon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class FavouriteCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)
    location: LatLon | None = None
    place_id: int | None = Field(default=None, ge=1)
    visibility: Visibility = "private"
    share_precision_m: Precision = 100

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        return _clean_label(v)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _clean_note(v)

    @model_validator(mode="after")
    def _one_position(self):
        if (self.location is None) == (self.place_id is None):
            raise ValueError("Provide exactly one of 'location' or 'place_id'.")
        return self


class FavouriteUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)
    location: LatLon | None = None
    visibility: Visibility | None = None
    share_precision_m: Precision | None = None

    @field_validator("label")
    @classmethod
    def _label(cls, v: str | None) -> str | None:
        return None if v is None else _clean_label(v)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return _clean_note(v)

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("Nothing to update.")
        if "label" in self.model_fields_set and self.label is None:
            raise ValueError("Label cannot be removed.")
        return self


class FavouriteOut(BaseModel):
    """OWNER view: exact location and private note."""

    id: uuid.UUID
    label: str
    note: str | None
    region: str
    location: LatLon
    place_id: int | None
    visibility: Visibility
    share_precision_m: Precision
    created_at: datetime
    updated_at: datetime
    has_photo: bool


class CloakedLocation(BaseModel):
    lat: float
    lon: float
    precision_m: Precision


class SharedFavouriteOut(BaseModel):
    """NON-OWNER view (share link or recipient). No exact coordinates, note, email or place."""

    label: str
    region: str
    location: CloakedLocation
    owner_display_name: str
    shared_at: datetime
    expires_at: datetime | None
    has_photo: bool


class ReceivedShareOut(SharedFavouriteOut):
    share_id: uuid.UUID


class PublicFavouriteOut(BaseModel):
    label: str
    region: str
    location: CloakedLocation
    owner_display_name: str
    created_at: datetime


class UserShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["user"]
    email: EmailStr = Field(max_length=254)
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 365)


class LinkShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["link"]
    expires_in_hours: int = Field(default=72, ge=1, le=24 * 30)  # links must expire, max 30 days


ShareCreateIn = Annotated[UserShareIn | LinkShareIn, Field(discriminator="type")]


class ShareOut(BaseModel):
    id: uuid.UUID
    type: Literal["user", "link"]
    recipient_display_name: str | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    # Only present in the creation response: the raw link token is never stored or shown again.
    token: str | None = None
    path: str | None = None


class CloakPreviewOut(BaseModel):
    """Owner-only preview of the cloaked view at one precision."""

    precision_m: Precision
    location: LatLon
    cell: list[tuple[float, float]]  # polygon ring as [lon, lat] pairs (GeoJSON order)
