"""Authentication endpoints: register, login, refresh (rotation), logout.

Token storage design (see docs):
  * access token  -> returned in the JSON body; the frontend keeps it in memory only.
  * refresh token -> HttpOnly + Secure + SameSite=Strict cookie, Path=/api/auth.
                     JavaScript can never read it, and it is only sent to auth endpoints.
  * CSRF          -> refresh/logout are cookie-authenticated, so they also require an
                     X-CSRF-Token header equal to the __Host-gv_csrf cookie (double submit).
Failure paths RETURN responses instead of raising, so the audit row in the same
transaction is committed rather than rolled back.
"""

import hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.database import Conn
from app.deps import AppSettings, get_login_limiter, get_register_limiter
from app.schemas.auth import AcceptedOut, LoginIn, RegisterIn, TokenOut
from app.security.audit import audit, client_ip
from app.security.rate_limit import LoginLimiter, RateLimiter
from app.security.tokens import create_access_token
from app.services import auth as svc

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "gv_refresh"
CSRF_COOKIE = "__Host-gv_csrf"
CSRF_HEADER = "X-CSRF-Token"
_REFRESH_PATH = "/api/auth"
_GENERIC_LOGIN_FAILURE = "Invalid email or password."
_REGISTER_ACCEPTED = "If this email can be registered, the account is ready: sign in to continue."


def _set_session_cookies(response: Response, refresh_raw: str, settings) -> None:
    max_age = settings.refresh_token_days * 86400
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_raw,
        max_age=max_age,
        path=_REFRESH_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=max_age,
        path="/",
        httponly=False,
        secure=True,
        samesite="strict",  # readable by our JS for the header
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=_REFRESH_PATH, httponly=True, secure=True, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, samesite="strict")


def _error(status_code: int, detail: str, clear_cookies: bool = False, headers=None) -> JSONResponse:
    resp = JSONResponse({"detail": detail}, status_code=status_code, headers=headers)
    if clear_cookies:
        _clear_session_cookies(resp)
    return resp


def _csrf_ok(request: Request) -> bool:
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    return bool(cookie and header) and hmac.compare_digest(cookie, header)


def _token_response(user_id, refresh_raw: str, settings) -> JSONResponse:
    token = create_access_token(
        user_id, settings.jwt_secret.get_secret_value(), settings.access_token_minutes
    )
    body = TokenOut(access_token=token, expires_in=settings.access_token_minutes * 60)
    resp = JSONResponse(body.model_dump(), headers={"Cache-Control": "no-store"})
    _set_session_cookies(resp, refresh_raw, settings)
    return resp


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedOut,
    responses={429: {"description": "Too many registrations from this client"}},
)
def register(
    body: RegisterIn,
    request: Request,
    conn: Conn,
    limiter: Annotated[RateLimiter, Depends(get_register_limiter)],
):
    ip = client_ip(request)
    if wait := limiter.retry_after(ip):
        return _error(429, "Too many requests. Try again later.", headers={"Retry-After": str(wait)})
    limiter.hit(ip)

    user_id = svc.register(conn, body.email, body.password, body.display_name)
    if user_id:
        audit(conn, request, "auth.register", actor_id=user_id, target_type="user", target_id=user_id)
    else:
        audit(conn, request, "auth.register_duplicate")  # no email stored
    # Identical response either way: registration cannot be used to test which emails exist.
    return AcceptedOut(detail=_REGISTER_ACCEPTED)


@router.post(
    "/login",
    response_model=TokenOut,
    responses={401: {"description": "Invalid credentials"}, 429: {"description": "Rate limited"}},
)
def login(
    body: LoginIn,
    request: Request,
    conn: Conn,
    settings: AppSettings,
    limiter: Annotated[LoginLimiter, Depends(get_login_limiter)],
):
    ip = client_ip(request)
    if wait := limiter.retry_after(body.email, ip):
        audit(conn, request, "auth.login_rate_limited")
        return _error(429, "Too many attempts. Try again later.", headers={"Retry-After": str(wait)})

    result = svc.authenticate(conn, body.email, body.password)
    if result.user_id is None:
        limiter.failed(body.email, ip)
        audit(conn, request, "auth.login_failure", target_type="user", target_id=result.known_account_id)
        return _error(401, _GENERIC_LOGIN_FAILURE)

    limiter.succeeded(body.email)
    refresh_raw, _ = svc.issue_refresh_token(conn, result.user_id, settings.refresh_token_days)
    audit(conn, request, "auth.login_success", actor_id=result.user_id)
    return _token_response(result.user_id, refresh_raw, settings)


@router.post(
    "/refresh",
    response_model=TokenOut,
    responses={401: {"description": "Missing, expired, revoked or reused refresh token"}, 403: {}},
)
def refresh(request: Request, conn: Conn, settings: AppSettings):
    if not _csrf_ok(request):
        return _error(403, "CSRF check failed.")
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return _error(401, "Not authenticated.")
    try:
        user_id, new_raw = svc.rotate_refresh_token(conn, raw, settings.refresh_token_days)
    except svc.RefreshTokenReuse as reuse:
        audit(conn, request, "auth.refresh_reuse_detected", target_type="user", target_id=reuse.user_id)
        return _error(401, "Session revoked. Sign in again.", clear_cookies=True)
    except svc.InvalidRefreshToken:
        return _error(401, "Session expired. Sign in again.", clear_cookies=True)
    audit(conn, request, "auth.refresh", actor_id=user_id)
    return _token_response(user_id, new_raw, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses={403: {}})
def logout(request: Request, conn: Conn):
    if not _csrf_ok(request):
        return _error(403, "CSRF check failed.")
    raw = request.cookies.get(REFRESH_COOKIE)
    user_id = svc.revoke_session(conn, raw) if raw else None
    if user_id:
        audit(conn, request, "auth.logout", actor_id=user_id)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookies(resp)
    return resp
