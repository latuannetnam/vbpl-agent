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


def test_incremental_release_reuses_unchanged_docs_and_writes_delta_manifest(tmp_path: Path) -> None:
    from vbpl_kb.catalog import parse_catalog_entry
    db_path = tmp_path / "state.sqlite3"
    st = StateStore.open(db_path)

    # Run 1: initial export with doc 100 and doc 200
    r1 = st.begin_run("run-1")
    e100 = parse_catalog_entry({"id": "100", "title": "Doc 100"})
    e200 = parse_catalog_entry({"id": "200", "title": "Doc 200"})
    st.record_catalog_scan(r1, [e100, e200], complete=True)

    st.record_snapshot(r1, "100", "detail", json.dumps({"data": {"id": "100", "title": "Doc 100", "fullText": "Điều 1. Text 100"}}), "hash100")
    st.record_snapshot(r1, "200", "detail", json.dumps({"data": {"id": "200", "title": "Doc 200", "fullText": "Điều 1. Text 200"}}), "hash200")
    st.record_status(StatusObservation(vbpl_id="100", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash100", run_id=r1))
    st.record_status(StatusObservation(vbpl_id="200", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash200", run_id=r1))
    st.finish_run(r1, "completed", 1.0)

    exporter = ReleaseExporter(st, tmp_path / "exports")
    m1 = exporter.write_candidate(r1)
    active1 = exporter.promote(m1)
    assert active1.release_id == "run-1"

    doc100_r1_bytes = (m1.manifest_path.parent / m1.documents[0]["relative_path"]).read_bytes()

    # Run 2: doc 100 unchanged (no snapshot in run-2), doc 200 updated (snapshot in run-2), doc 300 new
    r2 = st.begin_run("run-2")
    e200_v2 = parse_catalog_entry({"id": "200", "title": "Doc 200 Updated"})
    e300 = parse_catalog_entry({"id": "300", "title": "Doc 300 New"})
    st.record_catalog_scan(r2, [e100, e200_v2, e300], complete=True)

    st.record_snapshot(r2, "200", "detail", json.dumps({"data": {"id": "200", "title": "Doc 200 Updated", "fullText": "Điều 1. Text 200 Updated"}}), "hash200_v2")
    st.record_snapshot(r2, "300", "detail", json.dumps({"data": {"id": "300", "title": "Doc 300 New", "fullText": "Điều 1. Text 300"}}), "hash300")
    st.record_status(StatusObservation(vbpl_id="100", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash100", run_id=r2))
    st.record_status(StatusObservation(vbpl_id="200", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash200_v2", run_id=r2))
    st.record_status(StatusObservation(vbpl_id="300", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash300", run_id=r2))
    st.finish_run(r2, "completed", 1.0)

    m2 = exporter.write_candidate(r2)
    active2 = exporter.promote(m2)
    assert active2.release_id == "run-2"

    # Verify doc 100 in run-2 directory is identical to run-1
    doc100_r2_file = m2.manifest_path.parent / "documents" / "vbpl_100.json"
    assert doc100_r2_file.exists()
    assert doc100_r2_file.read_bytes() == doc100_r1_bytes

    # Verify delta-manifest.json exists
    delta_path = m2.manifest_path.parent / "delta-manifest.json"
    assert delta_path.exists()
    delta_data = json.loads(delta_path.read_text(encoding="utf-8"))
    assert delta_data["parent_release_id"] == "run-1"
    assert delta_data["release_id"] == "run-2"
    assert set(delta_data["upsert_ids"]) == {"vbpl:200", "vbpl:300"}

    # Verify pending delta batches in StateStore
    pending = st.pending_delta_batches()
    assert [p["release_id"] for p in pending] == ["run-1", "run-2"]

