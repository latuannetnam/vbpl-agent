import json
import pytest
from pathlib import Path
from datetime import datetime, UTC
from vbpl_kb.state import StateStore
from vbpl_kb.models import StatusObservation
from vbpl_kb.releases import ReleaseExporter, ReleaseManifest, ReleaseBlocked, _sha256_file


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


def make_manifest_with_projection_version(tmp_path: Path, version: int) -> ReleaseManifest:
    export_dir = tmp_path / "exports"
    rel_dir = export_dir / "releases" / "bad_ver"
    rel_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = rel_dir / "manifest.json"
    payload = {
        "release_id": "bad_ver",
        "projection_schema_version": version,
        "document_count": 0,
        "section_count": 0,
        "published_at": "",
        "documents": [],
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return ReleaseManifest(
        release_id="bad_ver",
        manifest_path=manifest_path.resolve(),
        manifest_sha256=_sha256_file(manifest_path),
        document_count=0,
        section_count=0,
        projection_schema_version=version,
    )


def test_candidate_contains_ordered_schema_v2_sections(tmp_path: Path, store: StateStore) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    manifest = exporter.write_candidate("good")
    payload = json.loads(
        (manifest.manifest_path.parent / manifest.documents[0]["relative_path"])
        .read_text(encoding="utf-8")
    )
    assert payload["projection_schema_version"] == 2
    assert payload["document_id"] == "vbpl:123"
    assert payload["sections"][0]["section_id"] == "dieu-1"
    assert payload["sections"][0]["link"].startswith("https://vbpl.vn/")
    assert manifest.section_count >= manifest.document_count


def test_unsupported_projection_blocks_promotion_and_keeps_pointer(tmp_path: Path, store: StateStore) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    prior = exporter.promote(exporter.write_candidate("good"))
    bad = make_manifest_with_projection_version(tmp_path, version=3)
    with pytest.raises(ReleaseBlocked, match="Unsupported projection schema"):
        exporter.promote(bad)
    assert exporter.read_active() == prior


def test_existing_candidate_is_revalidated_not_accepted_by_count_only(tmp_path: Path, store: StateStore) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    manifest = exporter.write_candidate("good")
    document = manifest.manifest_path.parent / manifest.documents[0]["relative_path"]
    document.write_text("{}", encoding="utf-8")
    with pytest.raises(ReleaseBlocked, match="checksum"):
        exporter.write_candidate("good")


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
