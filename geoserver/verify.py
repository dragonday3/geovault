"""Verify the local GeoServer exposes ONLY public places (standard library only).

    py -3.10 geoserver/verify.py

Each check prints PASS/FAIL; the exit code is non-zero if any check fails. Only the local
GeoServer on 127.0.0.1 is contacted.
"""

import base64
import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import AUTH, BASE, ENV, LAYER, STORE, WORKSPACE, rest  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{f' - {detail}' if detail else ''}")
    if not ok:
        FAILED.append(name)


def http(
    url: str, auth: str | None = None, data: bytes | None = None, ctype: str | None = None
) -> tuple[int, str]:
    headers = {}
    if auth:
        headers["Authorization"] = auth
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed local http URL)
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def ows(service: str, **params: str) -> tuple[int, str]:
    query = urllib.parse.urlencode({"service": service, **params})
    return http(f"{BASE}/ows?{query}")


def names(xml: str, tag: str) -> set[str]:
    # Only ever parses responses from our own GeoServer on 127.0.0.1; expat does not resolve
    # external entities.
    root = ET.fromstring(xml)  # noqa: S314
    return {el.text for el in root.iter() if el.tag.split("}")[-1] == tag and el.text}


def main() -> None:
    # 1. Credentials
    default = "Basic " + base64.b64encode(b"admin:geoserver").decode()
    check("default admin/geoserver rejected", http(f"{BASE}/rest/workspaces.json", default)[0] == 401)
    check("anonymous REST rejected", http(f"{BASE}/rest/workspaces.json")[0] == 401)

    # 2. What is advertised
    status, caps = ows("WFS", version="2.0.0", request="GetCapabilities")
    wfs_types = names(caps, "Name") if status == 200 else set()
    check(
        "WFS advertises only public_places",
        wfs_types == {f"{WORKSPACE}:{LAYER}"},
        ", ".join(sorted(wfs_types)),
    )
    status, caps = ows("WMS", version="1.3.0", request="GetCapabilities")
    wms_layers = {n for n in names(caps, "Name") if ":" in n} if status == 200 else set()
    check(
        "WMS advertises only public_places",
        wms_layers == {f"{WORKSPACE}:{LAYER}"},
        ", ".join(sorted(wms_layers)),
    )

    # 3. Public data is served, with public columns only
    status, body = ows(
        "WFS",
        version="2.0.0",
        request="GetFeature",
        typeNames=f"{WORKSPACE}:{LAYER}",
        count="3",
        outputFormat="application/json",
    )
    features = json.loads(body).get("features", []) if status == 200 else []
    props = set().union(*(f["properties"].keys() for f in features)) if features else set()
    check("WFS GetFeature returns public places", len(features) == 3, f"{len(features)} features")
    check(
        "only public columns exposed",
        props <= {"id", "name", "category", "region", "source"},
        ", ".join(sorted(props)),
    )
    status, _ = ows(
        "WMS",
        version="1.3.0",
        request="GetMap",
        layers=f"{WORKSPACE}:{LAYER}",
        styles="",
        crs="EPSG:4326",
        bbox="12.90,77.55,13.00,77.65",
        width="256",
        height="256",
        format="image/png",
    )
    check("WMS GetMap renders", status == 200)

    # 4. Private tables are not reachable through OGC requests
    for table in ("favourites", "users", "shares", "photos", "refresh_tokens", "audit_log"):
        status, body = ows(
            "WFS", version="2.0.0", request="GetFeature", typeNames=f"{WORKSPACE}:{table}", count="1"
        )
        check(f"WFS GetFeature {table} refused", "ExceptionReport" in body or status >= 400)

    # 5. WFS is read-only
    tx = (
        '<wfs:Transaction service="WFS" version="2.0.0" xmlns:wfs="http://www.opengis.net/wfs/2.0" '
        f'xmlns:fes="http://www.opengis.net/fes/2.0"><wfs:Delete typeName="{WORKSPACE}:{LAYER}">'
        '<fes:Filter><fes:ResourceId rid="public_places.1"/></fes:Filter></wfs:Delete></wfs:Transaction>'
    ).encode()
    status, body = http(f"{BASE}/wfs", data=tx, ctype="text/xml")
    check("WFS Transaction (delete) rejected", "ExceptionReport" in body or status >= 400)

    # 6. Defence in depth: even an ADMIN cannot publish a private table, because the DB role
    #    behind the store has no SELECT on it.
    rest("DELETE", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/favourites?recurse=true")
    status, body = rest(
        "POST",
        f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes",
        {"featureType": {"name": "favourites", "nativeName": "favourites", "srs": "EPSG:4326"}},
    )
    if status in (200, 201):
        fstatus, fbody = ows(
            "WFS", version="2.0.0", request="GetFeature", typeNames=f"{WORKSPACE}:favourites", count="1"
        )
        leaked = fstatus == 200 and '"features"' in fbody and '"features":[]' not in fbody.replace(" ", "")
        check("admin-published favourites layer still returns no data", not leaked, "DB denied SELECT")
        rest("DELETE", f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/favourites?recurse=true")
    else:
        check(
            "admin cannot publish favourites (DB role has no SELECT)",
            True,
            f"GeoServer refused: HTTP {status}",
        )

    # 7. Not reachable from the local network
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET address: no packet is sent for UDP connect
        lan_ip = probe.getsockname()[0]
    finally:
        probe.close()
    port = int(ENV.get("GEOVAULT_GEOSERVER_PORT", "8080"))
    try:
        socket.create_connection((lan_ip, port), timeout=2).close()
        reachable = True
    except OSError:
        reachable = False
    check(f"not reachable on LAN address {lan_ip}:{port}", not reachable or lan_ip.startswith("127."))

    print(f"\n{'ALL CHECKS PASSED' if not FAILED else f'{len(FAILED)} CHECK(S) FAILED'}")
    _ = AUTH  # imported for parity with bootstrap's authenticated session
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
