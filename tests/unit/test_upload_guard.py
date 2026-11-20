"""UploadGuard must reject before the application (and its multipart parser) ever runs."""

import asyncio

import pytest

from app.security.upload_guard import MULTIPART_OVERHEAD, UploadGuard

LIMIT = 1000


def run(method="POST", path="/api/favourites/x/photo", headers=()):
    calls, sent = [], []

    async def inner(scope, receive, send):
        calls.append(scope["path"])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    guard = UploadGuard(inner, max_bytes_getter=lambda: LIMIT)
    scope = {"type": "http", "method": method, "path": path, "headers": list(headers)}
    asyncio.run(guard(scope, receive, send))
    status = sent[0]["status"] if sent else None
    return calls, status


def test_oversized_declared_length_never_reaches_app():
    calls, status = run(headers=[(b"content-length", str(LIMIT + MULTIPART_OVERHEAD + 1).encode())])
    assert status == 413 and calls == []


def test_missing_content_length_never_reaches_app():
    calls, status = run(headers=[(b"transfer-encoding", b"chunked")])
    assert status == 411 and calls == []


@pytest.mark.parametrize("value", [b"-1", b"abc", b"1e9"])
def test_malformed_content_length_refused(value):
    calls, status = run(headers=[(b"content-length", value)])
    assert status == 411 and calls == []


def test_within_limit_and_other_routes_pass_through():
    assert run(headers=[(b"content-length", b"500")]) == (["/api/favourites/x/photo"], None)
    assert run(path="/api/auth/login") == (["/api/auth/login"], None)
    assert run(method="GET") == (["/api/favourites/x/photo"], None)
