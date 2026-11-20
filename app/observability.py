"""Structured JSON logging with redaction, request IDs, access logging and the central
500 handler.

Logging rules (enforced here, not left to each call site):
  * one JSON object per line: easy to ship to CloudWatch and to query;
  * every line from a request carries its request_id (also returned as X-Request-ID);
  * secrets and personal data are scrubbed from EVERY string before it is written:
    JWTs, bearer tokens, password/token/secret fields, emails, DB DSNs, share-link tokens and
    high-precision coordinates;
  * the access log records the path WITHOUT the query string: /api/places/near?lat=..&lon=..
    is a user's location, and share tokens travel in paths.
"""

import contextvars
import json
import logging
import re
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_REDACTIONS = [
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]*"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\bbearer\s+[\w.~+/-]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"postgres(?:ql)?://\S+"), "postgresql://[REDACTED]"),
    (
        re.compile(
            r"""(?ix)
            (["']?(?:password|passwd|secret|token|refresh_token|access_token|jwt|api_key|csrf)["']?
             \s*[:=]\s*)
            ("[^"]*"|'[^']*'|[^\s,}]+)
            """
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(/api/shared/)(?!with-me\b)[A-Za-z0-9_-]{20,}"), r"\1[REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[REDACTED_EMAIL]"),
    # 4+ decimal places ~ 11 m precision: treat as a location. (Durations are logged with 1 dp.)
    (re.compile(r"-?\b\d{1,3}\.\d{4,}\b"), "[REDACTED_COORD]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    _SKIP = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if rid := request_id_var.get():
            entry["request_id"] = rid
        for key, value in vars(record).items():
            if key not in self._SKIP and not key.startswith("_"):
                entry[key] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            entry["exc"] = redact("".join(traceback.format_exception(*record.exc_info)))
        return json.dumps(entry, default=str)


def configure_logging(stream=None, level: int = logging.INFO) -> logging.Handler:
    """Route everything (app and uvicorn) through one JSON handler. Returns the handler."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our redacting access log
    return handler


_access = logging.getLogger("geovault.access")
_errors = logging.getLogger("geovault.error")
_RID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_ERROR_HEADERS = [
    (b"content-type", b"application/json"),
    (b"cache-control", b"no-store"),
    (b"x-content-type-options", b"nosniff"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]


class RequestContext:
    """Outermost middleware: request ID, access log, and the single place unhandled
    exceptions become a generic 500 (details go to the log, never to the client)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _RID.match(incoming) else uuid.uuid4().hex  # never trust odd IDs
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            _errors.exception("unhandled exception")
            if not started:
                body = json.dumps({"detail": "Internal server error", "request_id": rid}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            *_ERROR_HEADERS,
                            (b"x-request-id", rid.encode()),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
            status = 500
        finally:
            client = scope.get("client")
            _access.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # query string deliberately omitted
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "client_ip": client[0] if client else None,
                },
            )
            request_id_var.reset(token)
