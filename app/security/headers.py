"""HTTP security headers on every response.

CSP: the frontend is self-hosted (vanilla JS, vendored Leaflet, no inline script or style
blocks), so the policy can be strict. The only third-party origin is the OSM tile server for
map images. Headers a route already set (e.g. the photo route's `sandbox` CSP) are kept.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

OSM_TILES = "https://tile.openstreetmap.org"

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        f"img-src 'self' data: {OSM_TILES}",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",  # clickjacking: nobody may frame GeoVault
    ]
)

# Swagger UI (local development only) needs its CDN bundle and an inline bootstrap script.
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)

BASE_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    # OSM's tile usage policy needs a Referer; send only our origin, never paths (share tokens).
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"permissions-policy": b"camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
    b"cross-origin-opener-policy": b"same-origin",
    b"cross-origin-resource-policy": b"same-origin",
}
HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecurityHeaders:
    def __init__(self, app: ASGIApp, production: bool, docs_paths: tuple[str, ...] = ()):
        self.app = app
        self.production = production
        self.docs_paths = docs_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        csp = (DOCS_CSP if path in self.docs_paths else CSP).encode()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = dict(BASE_HEADERS)
                extra[b"content-security-policy"] = csp
                if path.startswith("/api/"):
                    extra[b"cache-control"] = b"no-store"  # API data is never cached by default
                if self.production:  # HTTPS only: HSTS over plain HTTP is ignored/misleading
                    extra[HSTS[0]] = HSTS[1]
                headers += [(k, v) for k, v in extra.items() if k not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
