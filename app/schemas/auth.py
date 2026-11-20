"""Request/response models for authentication. extra="forbid" rejects unknown fields, so a
client cannot smuggle e.g. `role` into registration (mass assignment, OWASP API3)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.security.passwords import MAX_LENGTH, password_problem

DISPLAY_NAME = Field(min_length=1, max_length=60, pattern=r"^[^\x00-\x1f\x7f<>]+$")


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=MAX_LENGTH)
    display_name: str = DISPLAY_NAME

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Display name must not be blank.")
        return v

    @model_validator(mode="after")
    def _password_policy(self):
        problem = password_problem(self.password, self.email)
        if problem:
            raise ValueError(problem)
        return self


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=MAX_LENGTH)


class AcceptedOut(BaseModel):
    status: Literal["accepted"] = "accepted"
    detail: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (OAuth token type name, not a secret)
    expires_in: int


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Literal["user", "admin"]
    created_at: datetime
