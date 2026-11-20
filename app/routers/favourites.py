"""Favourites (owner CRUD), the public list, and share management.

Object-level authorization: every route with {favourite_id} takes it ONLY through the
OwnedFav dependency (get_owned_favourite), so a non-owner gets 404 before any handler code
runs. Static routes (/public) are declared before /{favourite_id} so they are not shadowed.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from app.database import Conn
from app.deps import AuthUser, OwnedFav, get_share_limiter, no_store
from app.schemas.favourites import (
    FavouriteCreateIn,
    FavouriteOut,
    FavouriteUpdateIn,
    PublicFavouriteOut,
    ShareCreateIn,
    ShareOut,
    UserShareIn,
)
from app.security.audit import audit
from app.security.rate_limit import RateLimiter
from app.services import favourites as favs
from app.services import sharing

router = APIRouter(prefix="/api/favourites", tags=["favourites"], dependencies=[Depends(no_store)])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10_000)]
RegionCode = Annotated[str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,30}$")]


@router.get("/public", response_model=list[PublicFavouriteOut])
def public_favourites(
    user: AuthUser, conn: Conn, region: RegionCode = None, limit: Limit = 50, offset: Offset = 0
):
    """Favourites their owners marked public: cloaked location and display name only."""
    return [sharing.to_shared_out(r) for r in favs.list_public(conn, region, limit, offset)]


@router.get("", response_model=list[FavouriteOut])
def list_favourites(user: AuthUser, conn: Conn, limit: Limit = 50, offset: Offset = 0):
    return [favs.to_owner_out(r) for r in favs.list_own(conn, user.id, limit, offset)]


@router.post("", response_model=FavouriteOut, status_code=status.HTTP_201_CREATED)
def create_favourite(body: FavouriteCreateIn, user: AuthUser, conn: Conn, request: Request):
    try:
        row = favs.create(conn, user.id, body)
    except favs.OutsideRegions:
        raise HTTPException(422, "Location is outside the supported regions.") from None
    except favs.PlaceNotFound:
        raise HTTPException(422, "Place not found.") from None
    except favs.TooManyFavourites:
        raise HTTPException(409, f"Limit of {favs.MAX_FAVOURITES_PER_USER} favourites reached.") from None
    audit(conn, request, "favourite.create", actor_id=user.id, target_type="favourite", target_id=row["id"])
    return favs.to_owner_out(row)


@router.get("/{favourite_id}", response_model=FavouriteOut)
def get_favourite(fav: OwnedFav, conn: Conn):
    return favs.to_owner_out(favs.get(conn, fav.id, fav.owner_id))


@router.patch("/{favourite_id}", response_model=FavouriteOut)
def update_favourite(body: FavouriteUpdateIn, fav: OwnedFav, user: AuthUser, conn: Conn, request: Request):
    try:
        row = favs.update(conn, fav.id, fav.owner_id, body)
    except favs.OutsideRegions:
        raise HTTPException(422, "Location is outside the supported regions.") from None
    audit(conn, request, "favourite.update", actor_id=user.id, target_type="favourite", target_id=fav.id)
    return favs.to_owner_out(row)


@router.delete("/{favourite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favourite(fav: OwnedFav, user: AuthUser, conn: Conn, request: Request):
    favs.delete(conn, fav.id, fav.owner_id)
    audit(conn, request, "favourite.delete", actor_id=user.id, target_type="favourite", target_id=fav.id)


# --- sharing -----------------------------------------------------------------------------------


@router.post(
    "/{favourite_id}/share",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {}, 409: {}, 429: {}},
)
def create_share(
    body: Annotated[ShareCreateIn, Body()],
    fav: OwnedFav,
    user: AuthUser,
    conn: Conn,
    request: Request,
    limiter: Annotated[RateLimiter, Depends(get_share_limiter)],
):
    # Rate-limited per user: user-shares reveal whether an email has an account, so bulk
    # probing through this endpoint is throttled (accepted, documented residual risk).
    key = str(user.id)
    if wait := limiter.retry_after(key):
        raise HTTPException(
            429, "Too many shares created. Try again later.", headers={"Retry-After": str(wait)}
        )
    limiter.hit(key)
    try:
        if isinstance(body, UserShareIn):
            share = sharing.share_with_user(conn, fav.id, fav.owner_id, body.email, body.expires_in_hours)
            action = "share.create_user"
        else:
            share, token = sharing.share_by_link(conn, fav.id, body.expires_in_hours)
            share = {**share, "token": token, "path": f"/api/shared/{token}"}
            action = "share.create_link"
    except sharing.ShareError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    audit(conn, request, action, actor_id=user.id, target_type="share", target_id=share["id"])
    return share


@router.get("/{favourite_id}/shares", response_model=list[ShareOut])
def list_shares(fav: OwnedFav, conn: Conn):
    return sharing.list_shares(conn, fav.id)


@router.delete("/{favourite_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(share_id: uuid.UUID, fav: OwnedFav, user: AuthUser, conn: Conn, request: Request):
    # The share must belong to THIS (owned) favourite, otherwise 404.
    if not sharing.revoke(conn, fav.id, share_id):
        raise HTTPException(404, "Share not found")
    audit(conn, request, "share.revoke", actor_id=user.id, target_type="share", target_id=share_id)
