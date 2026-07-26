from datetime import UTC, datetime
from vbpl_kb.models import LegalReference, StatusObservation
from vbpl_kb.state import StateStore

def test_snapshot_hash_and_latest_status(tmp_path) -> None:
    store = StateStore.open(tmp_path / "state.sqlite3")
    run_id = store.begin_run("vbpl-2026-07-21")
    assert store.record_snapshot(run_id, "123", "detail", '{"id":123}', "a") is True
    assert store.record_snapshot(run_id, "123", "detail", '{"id":123}', "a") is False
    status = StatusObservation(
        vbpl_id="123",
        eff_status="Còn hiệu lực",
        eff_from="2024-01-01",
        checked_at=datetime(2026, 7, 21, tzinfo=UTC),
        content_hash="a",
        run_id=run_id
    )
    store.record_status(status)
    assert store.latest_status("123") == status

def test_partial_run_cannot_replace_active_revision(tmp_path) -> None:
    store = StateStore.open(tmp_path / "state.sqlite3")
    # Start and complete a successful run
    run1 = store.begin_run("run-1")
    store.finish_run(run1, "completed", 1.0)
    store.set_active_run(run1)
    assert store.get_active_run_id() == "run-1"

    # Start a partial run
    run2 = store.begin_run("run-2")
    store.finish_run(run2, "partial", 0.99)
    # The active run is unchanged
    assert store.get_active_run_id() == "run-1"


def test_references_are_revision_scoped_and_deduplicated(tmp_path) -> None:
    store = StateStore.open(tmp_path / "state.sqlite3")
    reference = LegalReference(
        from_vbpl_id="187835",
        from_provision_key="whole",
        to_vbpl_id="175258",
        to_provision_key=None,
        relation_type="cites",
        evidence_kind="official_structured",
        evidence_reference="https://vbpl.vn",
        source_quote="VBPL structured reference: 63/2025/QH15",
        source_offset=None,
        resolution_state="verified",
        evidence_hash="a" * 64,
        corpus_revision="run-1",
        searchable=True,
    )

    store.record_reference("run-1", reference)
    store.record_reference("run-1", reference)
    store.record_reference("run-2", reference)

    rows = store.conn.execute(
        "SELECT run_id FROM legal_references ORDER BY run_id"
    ).fetchall()
    assert [row["run_id"] for row in rows] == ["run-1", "run-2"]


def test_release_runs_state(tmp_path) -> None:
    store = StateStore.open(tmp_path / "state.sqlite3")
    store.begin_run("run-1")
    store.record_release_run("run-1", "candidate", "/path/to/manifest.json", "sha123", 10)
    rel = store.get_release_run("run-1")
    assert rel is not None
    assert rel["status"] == "candidate"
    assert rel["document_count"] == 10

    store.record_release_run("run-1", "active", "/path/to/manifest.json", "sha123", 10)
    rel2 = store.get_release_run("run-1")
    assert rel2 is not None
    assert rel2["status"] == "active"


def test_catalog_scan_persistence_and_baseline(tmp_path) -> None:
    from vbpl_kb.catalog import parse_catalog_entry
    store = StateStore.open(tmp_path / "state.sqlite3")

    run_1 = store.begin_run("run-1")
    entry_a = parse_catalog_entry({"id": "100", "title": "Doc A", "effStatus": "Còn hiệu lực"})
    entry_b = parse_catalog_entry({"id": "200", "title": "Doc B", "effStatus": "Còn hiệu lực"})

    store.record_catalog_scan(run_1, [entry_a, entry_b], complete=True)
    
    baseline = store.latest_successful_catalog_entries()
    assert len(baseline) == 2
    assert baseline["100"].title == "Doc A"
    assert baseline["200"].title == "Doc B"


def test_partial_scan_cannot_replace_baseline(tmp_path) -> None:
    from vbpl_kb.catalog import parse_catalog_entry
    store = StateStore.open(tmp_path / "state.sqlite3")

    run_1 = store.begin_run("run-1")
    entry_a = parse_catalog_entry({"id": "100", "title": "Doc A Baseline"})
    store.record_catalog_scan(run_1, [entry_a], complete=True)

    # Run 2 fails partially with a partial catalog scan
    run_2 = store.begin_run("run-2")
    entry_b = parse_catalog_entry({"id": "999", "title": "Doc Partial"})
    store.record_catalog_scan(run_2, [entry_b], complete=False)

    # Baseline remains run_1
    baseline = store.latest_successful_catalog_entries()
    assert len(baseline) == 1
    assert "100" in baseline
    assert "999" not in baseline


def test_consecutive_absence_tombstone_lifecycle(tmp_path) -> None:
    from vbpl_kb.catalog import parse_catalog_entry
    store = StateStore.open(tmp_path / "state.sqlite3")

    # Run 1: baseline has 100, 200, 300
    run_1 = store.begin_run("run-1")
    entries_1 = [
        parse_catalog_entry({"id": "100", "title": "Doc 100"}),
        parse_catalog_entry({"id": "200", "title": "Doc 200"}),
        parse_catalog_entry({"id": "300", "title": "Doc 300"}),
    ]
    store.record_catalog_scan(run_1, entries_1, complete=True)

    # Run 2: 200 and 300 missing (1st complete scan absence)
    run_2 = store.begin_run("run-2")
    entries_2 = [parse_catalog_entry({"id": "100", "title": "Doc 100"})]
    store.record_catalog_scan(run_2, entries_2, complete=True)

    candidates, tombstones = store.update_removal_candidates({"100"}, run_2)
    assert set(candidates) == {"200", "300"}
    assert tombstones == []
    assert store.get_tombstone_ids() == []

    # Run 3: 200 missing again (2nd consecutive complete scan absence), 300 reappears!
    run_3 = store.begin_run("run-3")
    entries_3 = [
        parse_catalog_entry({"id": "100", "title": "Doc 100"}),
        parse_catalog_entry({"id": "300", "title": "Doc 300"}),
    ]
    store.record_catalog_scan(run_3, entries_3, complete=True)

    candidates_3, tombstones_3 = store.update_removal_candidates({"100", "300"}, run_3)
    assert candidates_3 == []
    assert tombstones_3 == ["200"]
    assert store.get_tombstone_ids() == ["200"]


def test_delta_batch_and_document_version_persistence(tmp_path) -> None:
    from vbpl_kb.models import DeltaManifest
    store = StateStore.open(tmp_path / "state.sqlite3")

    store.begin_run("run-1")
    store.record_document_version("100", "v1", "hash100", "run-1")

    manifest = DeltaManifest(
        release_id="rel-2",
        parent_release_id="rel-1",
        created_at="2026-07-26T10:00:00Z",
        upsert_ids=["100"],
        tombstone_ids=["200"],
        checksum_sha256="abc256",
    )
    store.record_delta_batch(manifest, manifest_path="/releases/rel-2/delta-manifest.json")

    pending = store.pending_delta_batches()
    assert len(pending) == 1
    assert pending[0]["release_id"] == "rel-2"
    assert pending[0]["upsert_ids"] == ["100"]
    assert pending[0]["tombstone_ids"] == ["200"]

    store.acknowledge_delta_batch(pending[0]["batch_id"])
    assert len(store.pending_delta_batches()) == 0


