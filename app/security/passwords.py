"""Password hashing (Argon2id) and password policy.

Policy follows NIST SP 800-63B: length over complexity rules, and rejection of passwords
known from breaches. No composition rules ("one symbol..."), which push users towards
predictable patterns.
"""

from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 12
MAX_LENGTH = 128  # Argon2 accepts more, but a cap stops megabyte "passwords" burning CPU.

# argon2-cffi defaults follow RFC 9106's recommended low-memory profile (Argon2id,
# t=3, m=64 MiB, p=4).
_hasher = PasswordHasher()

# Verifying against this when the email is unknown makes login take the same time whether
# or not the account exists (no timing-based user enumeration).
DUMMY_HASH = _hasher.hash("geovault-dummy-password-for-constant-time")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    path = Path(__file__).with_name("common_passwords.txt")
    lines = path.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line and not line.startswith("#"))


def password_problem(password: str, email: str | None = None) -> str | None:
    """Return a human-readable reason the password is unacceptable, or None if it is fine."""
    if len(password) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Password must be at most {MAX_LENGTH} characters."
    lowered = password.lower()
    if lowered in _common_passwords():
        return "This password appears in known data breaches. Choose a different one."
    if len(set(password)) < 4:
        return "Password is too repetitive."
    if email:
        local = email.split("@", 1)[0].lower()
        if len(local) >= 4 and local in lowered:
            return "Password must not contain your email address."
    return None
