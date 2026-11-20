"""The authenticated user's own account. (Profile edit, export and deletion: milestone 6.)"""

from fastapi import APIRouter, Response

from app.database import Conn
from app.deps import AuthUser
from app.schemas.auth import UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: AuthUser, conn: Conn, response: Response):
    response.headers["Cache-Control"] = "no-store"  # personal data must not be cached
    return conn.execute(
        "SELECT id, email, display_name, role, created_at FROM users WHERE id = %s",
        (user.id,),
    ).fetchone()
