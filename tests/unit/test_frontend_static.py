"""Static guards on the frontend: XSS-safe DOM usage, CSP compatibility, module integrity and
pinned third-party code."""

import base64
import hashlib
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SINKS = (
    r"\.innerHTML\s*=",
    r"\.outerHTML\s*=",
    r"insertAdjacentHTML",
    r"document\.write",
    r"\beval\(",
    r"new Function\(",
)


def app_scripts() -> list[Path]:
    files = sorted(p for p in FRONTEND.rglob("*.js") if "vendor" not in p.parts)
    assert len(files) >= 10, files  # guard against the scan silently matching nothing
    return files


def code_of(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("//")
    )


@pytest.mark.parametrize("path", app_scripts(), ids=lambda p: p.name)
def test_no_dangerous_dom_sinks(path):
    code = code_of(path)
    for sink in SINKS:
        assert not re.search(sink, code), f"{path.name}: dangerous DOM sink {sink}"
    assert "localStorage" not in code and "sessionStorage" not in code, "tokens must never be persisted"


@pytest.mark.parametrize("path", app_scripts(), ids=lambda p: p.name)
def test_relative_imports_resolve(path):
    for spec in re.findall(r'^import .*? from "(\.{1,2}/[^"]+)";', path.read_text(encoding="utf-8"), re.M):
        assert (path.parent / spec).resolve().is_file(), f"{path.name} imports missing module {spec}"


def test_no_inline_scripts_styles_or_handlers():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> blocks break a strict CSP"
    assert not re.search(r"\son[a-z]+\s*=", html), "inline event handlers break a strict CSP"
    assert not re.search(r"\sstyle\s*=", html), "inline style attributes break style-src 'self'"
    for path in app_scripts():
        assert 'setAttribute("style"' not in path.read_text(encoding="utf-8"), path.name


def test_vendored_leaflet_matches_sri_hashes():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for src, digest in re.findall(r'(?:href|src)="(/vendor/[^"]+)"\s+integrity="sha256-([^"]+)"', html):
        actual = base64.b64encode(hashlib.sha256((FRONTEND / src.lstrip("/")).read_bytes()).digest()).decode()
        assert actual == digest, f"{src} no longer matches its SRI hash"
    assert html.count('integrity="sha256-') == 2


def test_self_hosted_fonts_ship_with_licences():
    fonts = FRONTEND / "vendor" / "fonts"
    assert list(fonts.glob("archivo-*.woff2")) and list(fonts.glob("jetbrains-mono-*.woff2"))
    for lic in ("Archivo-OFL.txt", "JetBrainsMono-OFL.txt"):
        assert "SIL Open Font License" in (fonts / lic).read_text(encoding="utf-8")
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in css and "@import" not in css  # no third-party font CDN
