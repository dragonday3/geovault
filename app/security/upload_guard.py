"""Reject oversized photo uploads BEFORE the body is read (OWASP API4).

FastAPI parses multipart bodies before any route code or dependency runs, so a size check
inside the handler would only happen after the whole upload had been received and spooled.
This ASGI middleware looks at the declared Content-Length first:
  * missing (e.g. chunked transfer) -> 411 Length Required
  * larger than the limit           -> 413 Content Too Large
and also counts the bytes actually received, in case the declared length lies.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_OVERHEAD = 64 * 1024  # boundaries and part headers around the file


class UploadGuard:
    def __init__(self, app: ASGIApp, max_bytes_getter, path_suffix: str = "/photo"):
        self.app = app
        self.max_bytes_getter = max_bytes_getter
        self.path_suffix = path_suffix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].endswith(self.path_suffix)
        ):
            await self.app(scope, receive, send)
            return

        limit = self.max_bytes_getter() + MULTIPART_OVERHEAD
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is None or not declared.isdigit():
            await _reject(send, 411, b'{"detail":"Content-Length is required for uploads."}')
            return
        if int(declared) > limit:
            await _reject(send, 413, b'{"detail":"Photo is larger than the 5 MB limit."}')
            return

        received = 0

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:  # declared length was a lie: stop reading
                    raise ValueError("upload exceeded declared size")
            return message

        await self.app(scope, counted_receive, send)


async def _reject(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
