"""Open-data import pipeline: integrity check, provenance, idempotency, pruning."""

import json
import shutil

import psycopg
import pytest

import import_sources

KEY = "com-public-toilets"


@pytest.fixture
def imported(dsn, client):
    """Run the real import for one source, then remove everything it created."""
    manifest = json.loads((import_sources.RAW / "MANIFEST.json").read_text())
    yield manifest
    with psycopg.connect(dsn) as c:
        c.execute("DELETE FROM places WHERE source = %s", (KEY,))
        c.execute("DELETE FROM place_sources WHERE key = %s", (KEY,))


def test_import_records_provenance_and_is_idempotent(dsn, client, imported):
    meta = imported[KEY]
    with psycopg.connect(dsn) as c:
        first = import_sources.import_source(c, KEY, meta)
    with psycopg.connect(dsn) as c:
        second = import_sources.import_source(c, KEY, meta)

    assert first["inserted"] == meta["features"] and first["rejected"] == 0
    assert second["inserted"] == 0 and second["updated"] == meta["features"]

    src = {s["key"]: s for s in client.get("/api/sources?region=melbourne").json()}[KEY]
    assert src["licence"] == "CC BY 4.0"
    assert "City of Melbourne" in src["attribution"]


def test_import_prunes_rows_removed_from_snapshot(dsn, client, imported, tmp_path, monkeypatch):
    meta = dict(imported[KEY])
    with psycopg.connect(dsn) as c:
        import_sources.import_source(c, KEY, meta)

    # A smaller snapshot (first 10 features) with a matching manifest hash.
    data = json.loads((import_sources.RAW / meta["file"]).read_text(encoding="utf-8"))
    data["features"] = data["features"][:10]
    (tmp_path / meta["file"]).write_text(json.dumps(data), encoding="utf-8")
    import hashlib

    meta["sha256"] = hashlib.sha256((tmp_path / meta["file"]).read_bytes()).hexdigest()
    monkeypatch.setattr(import_sources, "RAW", tmp_path)

    with psycopg.connect(dsn) as c:
        stats = import_sources.import_source(c, KEY, meta)
        count = c.execute("SELECT count(*) FROM places WHERE source = %s", (KEY,)).fetchone()[0]
    assert stats["pruned"] == imported[KEY]["features"] - 10
    assert count == 10


def test_tampered_snapshot_is_refused_and_db_untouched(dsn, client, imported, tmp_path, monkeypatch):
    meta = imported[KEY]
    shutil.copy(import_sources.RAW / meta["file"], tmp_path / meta["file"])
    tampered = tmp_path / meta["file"]
    tampered.write_bytes(tampered.read_bytes().replace(b"Market Street", b"Market Streat", 1))
    monkeypatch.setattr(import_sources, "RAW", tmp_path)

    with psycopg.connect(dsn) as c, pytest.raises(RuntimeError, match="hash mismatch"):
        import_sources.import_source(c, KEY, meta)
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM places WHERE source = %s", (KEY,)).fetchone()[0] == 0


def test_committed_snapshots_match_manifest():
    import hashlib

    manifest = json.loads((import_sources.RAW / "MANIFEST.json").read_text())
    for key, meta in manifest.items():
        digest = hashlib.sha256((import_sources.RAW / meta["file"]).read_bytes()).hexdigest()
        assert digest == meta["sha256"], f"{key}: snapshot bytes changed (line endings?)"
