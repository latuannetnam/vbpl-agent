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
        source_quote="VBPL structured reference: 63/2025/QH15",
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

