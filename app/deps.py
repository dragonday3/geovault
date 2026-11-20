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
