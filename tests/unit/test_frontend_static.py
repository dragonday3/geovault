"""Static guards on the frontend: XSS-safe DOM usage and pinned third-party code."""

import base64
import hashlib
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def test_no_innerhtml_or_dangerous_sinks():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    code = "\n".join(line for line in js.splitlines() if not line.strip().startswith("//"))
    for sink in (
        r"\.innerHTML\s*=",
        r"\.outerHTML\s*=",
        r"insertAdjacentHTML",
        r"document\.write",
        r"\beval\(",
    ):
        assert not re.search(sink, code), f"dangerous DOM sink used: {sink}"


def test_no_inline_scripts_or_handlers():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> blocks break a strict CSP"
    assert not re.search(r"\son[a-z]+\s*=", html), "inline event handlers break a strict CSP"


def test_vendored_leaflet_matches_sri_hashes():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for src, digest in re.findall(r'(?:href|src)="(/vendor/[^"]+)"\s+integrity="sha256-([^"]+)"', html):
        actual = base64.b64encode(hashlib.sha256((FRONTEND / src.lstrip("/")).read_bytes()).digest()).decode()
        assert actual == digest, f"{src} no longer matches its SRI hash"
    assert html.count('integrity="sha256-') == 2
