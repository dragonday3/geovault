"""Log redaction and JSON formatting."""

import json
import logging
import sys

import pytest

from app.observability import JsonFormatter, redact, request_id_var

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLXZhbHVl"


@pytest.mark.parametrize(
    "raw, secret",
    [
        (f"token issued {JWT}", JWT),
        ("Authorization: Bearer abc.def-ghi_123", "abc.def-ghi_123"),
        ('{"password": "hunter2 is my pw"}', "hunter2 is my pw"),
        ("password=letmein123 user=x", "letmein123"),
        ("refresh_token='r4nd0m-t0k3n'", "r4nd0m-t0k3n"),
        ("csrf: abcdef123456", "abcdef123456"),
        ("user alice.smith+tag@example.com logged in", "alice.smith+tag@example.com"),
        ("connect postgresql://geovault_app:s3cret@db:5432/geovault failed", "s3cret"),
        ("GET /api/shared/Zm9vYmFyYmF6cXV4cXV1eGNvcmdl/photo", "Zm9vYmFyYmF6cXV4cXV1eGNvcmdl"),
        ("favourite at -37.81361, 144.96312", "-37.81361"),
        ("favourite at -37.81361, 144.96312", "144.96312"),
        ("near 12.97559,77.60673", "77.60673"),
    ],
)
def test_redacts_secrets_and_personal_data(raw, secret):
    assert secret not in redact(raw)


def test_keeps_useful_non_sensitive_text():
    line = "GET /api/shared/with-me 200 in 12.3 ms, places=21"
    assert redact(line) == line


def test_json_formatter_redacts_message_extras_and_tracebacks():
    fmt = JsonFormatter()
    try:
        raise ValueError("bad password=topsecret123 for bob@example.com")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "geovault.test", logging.ERROR, __file__, 1, "login for %s", ("bob@example.com",), exc_info
    )
    record.detail = f"jwt {JWT}"
    token = request_id_var.set("req-12345678")
    try:
        entry = json.loads(fmt.format(record))
    finally:
        request_id_var.reset(token)
    blob = json.dumps(entry)
    assert entry["request_id"] == "req-12345678" and entry["level"] == "ERROR"
    assert "ValueError" in entry["exc"]
    for leak in ("bob@example.com", "topsecret123", JWT):
        assert leak not in blob
