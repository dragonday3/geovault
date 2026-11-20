"""Access tokens (short-lived JWT) and refresh tokens (opaque, rotated, stored hashed).

Access token: HS256 JWT, 15 min, carries only the user id. Role is NOT in the token;
authorization reads it from the database on each request, so a demotion takes effect
immediately and a forged role claim is meaningless.

Refresh token: 256-bit random opaque string. Only its SHA-256 digest is stored.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"
ISSUER = "geovault"
AUDIENCE = "geovault-api"


class InvalidToken(Exception):
    pass


def create_access_token(user_id: uuid.UUID, secret: str, minutes: int) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=minutes),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "typ": "access",
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> uuid.UUID:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],  # pinned: rejects alg=none and algorithm confusion
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "nbf", "sub", "iss", "aud"]},
        )
        if claims.get("typ") != "access":
            raise InvalidToken("wrong token type")
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidToken(str(exc)) from None


def new_refresh_token() -> tuple[str, bytes]:
    """Return (raw token for the client cookie, SHA-256 digest for the database)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> bytes:
    # A plain SHA-256 is sufficient: the token is 256 bits of randomness, so there is
    # nothing to brute-force (unlike passwords, which need a slow hash).
    return hashlib.sha256(raw.encode()).digest()
