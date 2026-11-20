"""The authenticated user's own account: profile, edit, export, delete.

Identity always comes from the access token (AuthUser). There is no user id in any path or
body here, so one user cannot address another user's account (no BOLA surface).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.database import Conn
from app.deps import AuthUser, get_login_limiter, no_store
from app.routers.auth import _clear_session_cookies
from app.schemas.auth import UserOut
from app.schemas.users import DeleteAccountIn, UserUpdateIn
from app.security.audit import audit, client_ip
from app.security.passwords import verify_password
from app.security.rate_limit import LoginLimiter
from app.services import users as svc

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(no_store)])


@router.get("/me", response_model=UserOut)
def me(user: AuthUser, conn: Conn):
    return conn.execute(
        "SELECT id, email, display_name, role, created_at FROM users WHERE id = %s",
        (user.id,),
    ).fetchone()


@router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdateIn, user: AuthUser, conn: Conn, request: Request):
    row = svc.update_display_name(conn, user.id, body.display_name)
    audit(conn, request, "user.profile_update", actor_id=user.id, target_type="user", target_id=user.id)
    return row


@router.get("/me/export", responses={200: {"description": "JSON file with all of your data"}})
def export_me(user: AuthUser, conn: Conn, request: Request):
    data = svc.export_data(conn, user.id)
    audit(conn, request, "user.export", actor_id=user.id, target_type="user", target_id=user.id)
    return JSONResponse(
        jsonable_encoder(data),
        headers={
            "Content-Disposition": 'attachment; filename="geovault-export.json"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"description": "Password incorrect"}, 409: {"description": "Last administrator"}},
)
def delete_me(
    body: DeleteAccountIn,
    user: AuthUser,
    conn: Conn,
    request: Request,
    limiter: Annotated[LoginLimiter, Depends(get_login_limiter)],
):
    ip = client_ip(request)
    if wait := limiter.retry_after(user.email, ip):
        return JSONResponse(
            {"detail": "Too many attempts. Try again later."}, 429, headers={"Retry-After": str(wait)}
        )
    pw_hash = conn.execute("SELECT password_hash FROM users WHERE id = %s", (user.id,)).fetchone()
    if not verify_password(pw_hash["password_hash"], body.password):
        limiter.failed(user.email, ip)
        audit(conn, request, "user.delete_denied", actor_id=user.id, target_type="user", target_id=user.id)
        return JSONResponse({"detail": "Password is incorrect."}, status.HTTP_403_FORBIDDEN)

    # Audit first, while the actor still exists; the row survives anonymisation.
    audit(conn, request, "user.delete", actor_id=user.id, target_type="user", target_id=user.id)
    try:
        svc.delete_account(conn, user.id)
    except svc.LastAdminError as exc:
        conn.rollback()
        return JSONResponse({"detail": str(exc)}, status.HTTP_409_CONFLICT)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookies(resp)
    return resp
