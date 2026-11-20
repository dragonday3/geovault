"""Non-owner access to favourites: by share link (no account needed) or as a recipient.

Responses use SharedFavouriteOut: cloaked location, label, owner display name, dates.
Never the note, exact coordinates, the owner's email, or the linked public place (which
would reveal the exact position).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from app.database import Conn
from app.deps import AuthUser, PhotoStoreDep, no_store, photo_response
from app.schemas.favourites import ReceivedShareOut, SharedFavouriteOut
from app.security.audit import audit
from app.services import photos, sharing

router = APIRouter(prefix="/api/shared", tags=["sharing"], dependencies=[Depends(no_store)])


@router.get("/with-me", response_model=list[ReceivedShareOut])
def shared_with_me(user: AuthUser, conn: Conn):
    return [sharing.to_shared_out(r) for r in sharing.received(conn, user.id)]


Token = Annotated[str, Path(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]


def _shared_photo(conn, store, row):
    photo = photos.for_favourite(conn, row["favourite_id"]) if row else None
    if photo is None:
        raise HTTPException(404, "Share not found or no longer available")
    resp = photo_response(store, photo)
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@router.get("/with-me/{share_id}/photo", responses={200: {"content": {"image/*": {}}}, 404: {}})
def shared_with_me_photo(share_id: uuid.UUID, user: AuthUser, conn: Conn, store: PhotoStoreDep):
    rows = [r for r in sharing.received(conn, user.id) if r["share_id"] == share_id]
    return _shared_photo(conn, store, rows[0] if rows else None)


@router.get("/{token}/photo", responses={200: {"content": {"image/*": {}}}, 404: {}})
def shared_link_photo(token: Token, conn: Conn, store: PhotoStoreDep):
    # Same validity rules as the link view: not revoked, not expired, not private.
    return _shared_photo(conn, store, sharing.view_by_token(conn, token))


@router.get("/{token}", response_model=SharedFavouriteOut, responses={404: {}})
def view_shared_link(
    token: Token,
    conn: Conn,
    request: Request,
    response: Response,
):
    # The token sits in the URL: stop it leaking to other sites via the Referer header.
    response.headers["Referrer-Policy"] = "no-referrer"
    row = sharing.view_by_token(conn, token)
    if row is None:
        # Same 404 for unknown, expired, revoked or now-private: no oracle about which.
        raise HTTPException(404, "Share not found or no longer available")
    audit(conn, request, "share.link_view", target_type="share", target_id=row["share_id"])
    return sharing.to_shared_out(row)
