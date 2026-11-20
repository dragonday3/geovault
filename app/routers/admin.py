"""Administration. Every route depends on require_admin (server-side role check from the DB),
applied at router level so a newly added admin route cannot forget it."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database import Conn
from app.deps import AdminUser, no_store, require_admin
from app.schemas.users import AdminUserOut, AuditEntryOut, RoleUpdateIn
from app.security.audit import audit
from app.services import users as svc

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin), Depends(no_store)],
)

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100_000)]


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    conn: Conn,
    limit: Limit = 50,
    offset: Offset = 0,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    include_deleted: bool = False,
):
    pattern = None
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return conn.execute(
        """
        SELECT id, email, display_name, role, created_at, last_login_at, deleted_at
        FROM users
        WHERE (%(deleted)s OR deleted_at IS NULL)
          AND (%(p)s::text IS NULL OR email ILIKE %(p)s OR display_name ILIKE %(p)s)
        ORDER BY created_at DESC, id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {"deleted": include_deleted, "p": pattern, "limit": limit, "offset": offset},
    ).fetchall()


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserOut,
    responses={404: {"description": "No such active user"}, 409: {"description": "Own role"}},
)
def change_role(user_id: uuid.UUID, body: RoleUpdateIn, admin: AdminUser, conn: Conn, request: Request):
    if user_id == admin.id:
        # Prevents an admin locking everyone out by demoting the last admin (themselves).
        raise HTTPException(409, "Administrators cannot change their own role.")
    row, previous = svc.set_role(conn, user_id, body.role)
    if row is None:
        raise HTTPException(404, "User not found")
    if previous != body.role:
        action = "admin.role_grant_admin" if body.role == "admin" else "admin.role_revoke_admin"
        audit(conn, request, action, actor_id=admin.id, target_type="user", target_id=user_id)
    return row


@router.get("/audit", response_model=list[AuditEntryOut])
def audit_log(
    admin: AdminUser,
    conn: Conn,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
    action: Annotated[str | None, Query(pattern=r"^[a-z]+(\.[a-z_]+)*$", max_length=60)] = None,
    actor_id: uuid.UUID | None = None,
):
    # Viewing the audit trail is itself audited: administrators are also accountable.
    audit(conn, request, "admin.audit_view", actor_id=admin.id)
    return conn.execute(
        """
        SELECT a.id, a.actor_id, u.display_name AS actor_display_name, a.action,
               a.target_type, a.target_id, host(a.ip) AS ip, a.user_agent, a.created_at
        FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id
        WHERE (%(action)s::text IS NULL OR a.action = %(action)s OR a.action LIKE %(prefix)s)
          AND (%(actor)s::uuid IS NULL OR a.actor_id = %(actor)s)
        ORDER BY a.id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            "action": action,
            "prefix": f"{action}.%" if action else None,
            "actor": actor_id,
            "limit": limit,
            "offset": offset,
        },
    ).fetchall()
