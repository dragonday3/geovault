"""Config hardening, password hashing/policy, rate limiter. No database needed."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.security import passwords
from app.security.rate_limit import LoginLimiter, RateLimiter

DSN = "postgresql://u:p@localhost/db"


@pytest.mark.parametrize("secret", ["secret", "x" * 64, "short-but-random-Q7#", "changeme" * 5])
def test_weak_jwt_secrets_refuse_to_start(secret):
    with pytest.raises(ValidationError):
        Settings(database_url=DSN, jwt_secret=secret)


def test_token_lifetimes_are_capped():
    good = "Zq8x-" + "abcdefghijklmnopqrstuvwxyz0123456789"
    with pytest.raises(ValidationError):
        Settings(database_url=DSN, jwt_secret=good, access_token_minutes=60 * 24 * 7)
    with pytest.raises(ValidationError):
        Settings(database_url=DSN, jwt_secret=good, refresh_token_days=365)


def test_argon2id_hash_and_verify():
    h = passwords.hash_password("a perfectly fine passphrase")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password(h, "a perfectly fine passphrase")
    assert not passwords.verify_password(h, "a perfectly fine passphrasf")
    assert not passwords.verify_password("not-a-hash", "anything")


def test_hashes_are_salted():
    assert passwords.hash_password("same password here") != passwords.hash_password("same password here")


def test_breached_list_is_loaded_and_case_insensitive():
    assert passwords.password_problem("PasswordPassword") is not None
    assert passwords.password_problem("unusual-quokka-telescope-19") is None


def test_rate_limiter_window():
    rl = RateLimiter(limit=2, window_seconds=60)
    assert rl.retry_after("k") == 0
    rl.hit("k")
    rl.hit("k")
    assert rl.retry_after("k") > 0
    assert rl.retry_after("other") == 0


def test_login_limiter_tracks_account_and_ip_and_resets_on_success():
    lim = LoginLimiter(per_account=2, per_ip=3, window_seconds=60)
    lim.failed("A@x.com", "1.1.1.1")
    lim.failed("a@x.com", "2.2.2.2")  # case-insensitive account key
    assert lim.retry_after("a@x.com", "9.9.9.9") > 0
    lim.succeeded("a@x.com")
    assert lim.retry_after("a@x.com", "9.9.9.9") == 0
    for email in ("b@x.com", "c@x.com", "d@x.com"):
        lim.failed(email, "3.3.3.3")
    assert lim.retry_after("new@x.com", "3.3.3.3") > 0  # password spraying from one IP
