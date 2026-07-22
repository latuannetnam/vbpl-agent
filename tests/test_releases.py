import json
import pytest
from pathlib import Path
from datetime import datetime, UTC
from vbpl_kb.state import StateStore
from vbpl_kb.models import StatusObservation
from vbpl_kb.releases import ReleaseExporter, ReleaseManifest, ReleaseBlocked


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    db_path = tmp_path / "state.sqlite3"
    st = StateStore.open(db_path)
    run_id = "good"
    st.begin_run(run_id)
    st.record_snapshot(run_id, "123", "detail", json.dumps({"data": {"id": "123", "title": "Test Doc", "fullText": "Điều 1. Test"}}), "hash123")
    st.record_status(StatusObservation(
        vbpl_id="123",
        eff_status="Còn hiệu lực",
        eff_from="2024-01-01",
        checked_at=datetime(2026, 7, 22, tzinfo=UTC),
        content_hash="hash123",
        run_id=run_id
    ))
    st.finish_run(run_id, "completed", 1.0)
    return st


def test_invalid_candidate_does_not_replace_existing_pointer(tmp_path: Path, store: StateStore) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    active = exporter.promote(exporter.write_candidate("good"))
    with pytest.raises(ReleaseBlocked, match="checksum"):
        exporter.promote(ReleaseManifest(
            release_id="bad",
            manifest_path=tmp_path / "missing" / "manifest.json",
            manifest_sha256="bad",
            document_count=1
        ))
    assert exporter.read_active() == active


def test_candidate_write_and_promotion_success(tmp_path: Path, store: StateStore) -> None:
    export_dir = tmp_path / "exports"
    exporter = ReleaseExporter(store, export_dir)
    manifest = exporter.write_candidate("good")
    assert manifest.release_id == "good"
    assert manifest.document_count == 1
    assert manifest.manifest_path.exists()

    active = exporter.promote(manifest)
    assert active.release_id == "good"
    assert (export_dir / "active-release.json").exists()
    assert exporter.read_active() == active


def test_incomplete_run_rejects_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    st = StateStore.open(db_path)
    run_id = "partial"
    st.begin_run(run_id)
    st.finish_run(run_id, "partial", 0.8)

    exporter = ReleaseExporter(st, tmp_path / "exports")
    with pytest.raises(ReleaseBlocked, match="incomplete"):
        exporter.write_candidate(run_id)

