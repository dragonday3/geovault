"""Account self-service and admin models. Every input model forbids unknown fields, so
`{"role": "admin"}` sent to PATCH /api/users/me is a 422, not a privilege escalation."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import DISPLAY_NAME
from app.security.passwords import MAX_LENGTH

Role = Literal["user", "admin"]


class UserUpdateIn(BaseModel):
    """Only display_name is user-editable. Email and role are deliberately absent."""

    model_config = ConfigDict(extra="forbid")
    display_name: str = DISPLAY_NAME

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Display name must not be blank.")
        return v


class DeleteAccountIn(BaseModel):
    """Re-authentication for an irreversible action: a stolen access token alone cannot delete."""

    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=MAX_LENGTH)


class RoleUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    created_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None


class AuditEntryOut(BaseModel):
    id: int
    actor_id: uuid.UUID | None
    actor_display_name: str | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    user_agent: str | None
    created_at: datetime
