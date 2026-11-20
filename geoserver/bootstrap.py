"""Configure the local GeoServer through its REST API (idempotent, standard library only).

    docker compose --profile geoserver up -d
    py -3.10 geoserver/bootstrap.py

Result:
  * workspace `geovault`;
  * PostGIS store `geovault_public`, connecting as geoserver_ro. That DB role can SELECT the
    public_places view and nothing else, so no GeoServer setting can expose private tables;
  * one published layer, `geovault:public_places` (WMS + WFS);
  * WFS service level BASIC, which is read-only: no Transaction (insert/update/delete) operations;
  * WCS disabled (no raster data is published).

Credentials come from the repository's .env (GEOSERVER_ADMIN_*, GEOVAULT_GEOSERVER_DB_PASSWORD).
"""

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = "geovault"
STORE = "geovault_public"
LAYER = "public_places"


def load_env() -> dict[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


ENV = load_env()
BASE = f"http://127.0.0.1:{ENV.get('GEOVAULT_GEOSERVER_PORT', '8080')}/geoserver"
AUTH = (
    "Basic "
    + base64.b64encode(
        f"{ENV.get('GEOSERVER_ADMIN_USER', 'gvadmin')}:{ENV['GEOSERVER_ADMIN_PASSWORD']}".encode()
    ).decode()
)


def rest(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(  # noqa: S310 (fixed local http://127.0.0.1 base URL)
        f"{BASE}/rest{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": AUTH, "Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed local http URL)
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def wait_until_up(timeout_s: int = 240) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            status, _ = rest("GET", "/about/version.json")
            if status == 200:
                return
            if status == 401:
                sys.exit("GeoServer rejected the admin credentials from .env.")
        except OSError:
            pass
        time.sleep(3)
    sys.exit("GeoServer did not come up in time.")


def ensure(label: str, exists_path: str, create_path: str, body: dict) -> None:
    if rest("GET", exists_path)[0] == 200:
        print(f"  {label}: already present")
        return
    status, text = rest("POST", create_path, body)
    if status not in (200, 201):
        sys.exit(f"  {label}: failed ({status}) {text[:300]}")
    print(f"  {label}: created")


def main() -> None:
    print(f"Waiting for GeoServer at {BASE} ...")
    wait_until_up()

    ensure("workspace", f"/workspaces/{WORKSPACE}.json", "/workspaces", {"workspace": {"name": WORKSPACE}})

    store_params = {
        "dbtype": "postgis",
        "host": "db",
        "port": "5432",
        "database": "geovault",
        "schema": "public",
        "user": "geoserver_ro",
        "passwd": ENV["GEOVAULT_GEOSERVER_DB_PASSWORD"],
        "Expose primary keys": "false",
        "validate connections": "true",
        "max connections": "5",
    }
    ensure(
        "datastore",
        f"/workspaces/{WORKSPACE}/datastores/{STORE}.json",
        f"/workspaces/{WORKSPACE}/datastores",
        {
            "dataStore": {
                "name": STORE,
                "connectionParameters": {"entry": [{"@key": k, "$": v} for k, v in store_params.items()]},
            }
        },
    )
    ensure(
        "layer",
        f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes/{LAYER}.json",
        f"/workspaces/{WORKSPACE}/datastores/{STORE}/featuretypes",
        {
            "featureType": {
                "name": LAYER,
                "nativeName": LAYER,
                "title": "GeoVault public places",
                "abstract": "Public open data: City of Melbourne (CC BY 4.0) and OpenStreetMap (ODbL).",
                "srs": "EPSG:4326",
                "enabled": True,
            }
        },
    )

    status, _ = rest("PUT", "/services/wfs/settings", {"wfs": {"serviceLevel": "BASIC", "maxFeatures": 5000}})
    print(f"  WFS read-only (BASIC): {'ok' if status == 200 else status}")
    status, _ = rest("PUT", "/services/wcs/settings", {"wcs": {"enabled": False}})
    print(f"  WCS disabled: {'ok' if status == 200 else status}")
    print("Done. Verify with: py -3.10 geoserver/verify.py")


if __name__ == "__main__":
    main()
