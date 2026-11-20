"""Centralised request dependencies: settings, authentication, rate limiters.

Every protected endpoint gets the caller's identity ONLY from get_current_user, which
derives it from a verified access token plus a live database lookup. Nothing about who
the caller is, or what role they hold, is ever taken from the request body or the JWT.
"""

import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import Settings
from app.database import Conn
from app.security.rate_limit import LoginLimiter, RateLimiter
from app.security.tokens import InvalidToken, decode_access_token
from app.services.photos import LocalPhotoStore, PhotoLimits

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
)


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Literal["user", "admin"]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_login_limiter(request: Request) -> LoginLimiter:
    return request.app.state.login_limiter


def get_register_limiter(request: Request) -> RateLimiter:
    return request.app.state.register_limiter


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_current_user(
    conn: Conn,
    settings: AppSettings,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if creds is None:
        raise _UNAUTHORIZED
    try:
        user_id = decode_access_token(creds.credentials, settings.jwt_secret.get_secret_value())
    except InvalidToken:
        raise _UNAUTHORIZED from None
    row = conn.execute(
        "SELECT id, email, display_name, role FROM users WHERE id = %s AND deleted_at IS NULL",
        (user_id,),
    ).fetchone()
    if row is None:  # deleted after the token was issued
        raise _UNAUTHORIZED
    return CurrentUser(**row)


AuthUser = Annotated[CurrentUser, Depends(get_current_user)]


def require_admin(user: AuthUser) -> CurrentUser:
    """Function-level authorization (OWASP API5). The role comes from the users row loaded
    in get_current_user, so it reflects promotions/demotions immediately."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return user


AdminUser = Annotated[CurrentUser, Depends(require_admin)]


def no_store(response: Response) -> None:
    """Personal and administrative responses must never be cached by browsers or proxies."""
    response.headers["Cache-Control"] = "no-store"


class OwnedFavourite(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID


def get_owned_favourite(favourite_id: uuid.UUID, user: AuthUser, conn: Conn) -> OwnedFavourite:
    """Object-level authorization (OWASP API1). The ONLY way favourite routes obtain a
    favourite id: it must exist AND belong to the caller. Someone else's favourite gets the
    same 404 as a missing one, so ids cannot be probed for existence.

    UUIDs make ids unguessable, but they are not authorization: this check is.
    """
    row = conn.execute(
        "SELECT id, owner_id FROM favourites WHERE id = %s AND owner_id = %s",
        (favourite_id, user.id),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Favourite not found")
    return OwnedFavourite(**row)


OwnedFav = Annotated[OwnedFavourite, Depends(get_owned_favourite)]


def get_share_limiter(request: Request) -> RateLimiter:
    return request.app.state.share_limiter


def get_photo_limits(request: Request):
    return request.app.state.photo_limits


def get_photo_store(request: Request):
    return request.app.state.photo_store


PhotoStoreDep = Annotated[LocalPhotoStore, Depends(get_photo_store)]
PhotoLimitsDep = Annotated[PhotoLimits, Depends(get_photo_limits)]


def photo_response(store, photo: dict) -> Response:
    """Serve a stored photo safely. The content type comes from our own DB row (set from the
    decoded format), never from the client; the extra headers make the browser treat the
    bytes strictly as an image even if something went wrong upstream."""
    return Response(
        content=store.get(photo["storage_key"]),
        media_type=photo["content_type"],
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Content-Disposition": 'inline; filename="photo"',
            "Cache-Control": "private, no-store",
        },
    )
