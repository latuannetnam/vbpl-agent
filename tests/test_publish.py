import pytest
from datetime import datetime, UTC
from vbpl_kb.state import StateStore
from vbpl_kb.models import StatusObservation
from vbpl_kb.publish import Publisher, PublishBlocked

class FakeOnyxIngestionClient:
    def __init__(self):
        self.upserted = []
        self.deleted = []

    def healthcheck(self) -> bool:
        return True

    def upsert(self, doc) -> None:
        self.upserted.append(doc)

    def delete(self, doc_id: str) -> None:
        self.deleted.append(doc_id)

@pytest.fixture
def store(tmp_path):
    return StateStore.open(tmp_path / "state.sqlite3")

@pytest.fixture
def fake_onyx():
    return FakeOnyxIngestionClient()

def test_partial_run_is_blocked(store, fake_onyx) -> None:
    run_id = store.begin_run("vbpl-2026-07-21")
    store.finish_run(run_id, "partial", 0.99)
    with pytest.raises(PublishBlocked, match="crawl run is not complete"):
        Publisher(store, fake_onyx).publish(run_id)

def test_successful_publish(store, fake_onyx) -> None:
    run_id = store.begin_run("vbpl-2026-07-21")
    store.record_snapshot(run_id, "123", "detail", '{"data": {"id":123, "title": "Doc 123", "fullText": "Điều 1. X"}}', "hash1")
    obs = StatusObservation(
        vbpl_id="123",
        eff_status="Còn hiệu lực",
        eff_from="2024-01-01",
        checked_at=datetime.now(UTC),
        content_hash="hash1",
        run_id=run_id
    )
    store.record_status(obs)
    store.finish_run(run_id, "completed", 1.0)
    
    summary = Publisher(store, fake_onyx).publish(run_id)
    assert summary.upserted_count == 1
    assert len(fake_onyx.upserted) == 1
    assert fake_onyx.upserted[0].document_id == "vbpl:123"
    assert store.get_active_run_id() == run_id


def test_successful_publish_reports_progress(store, fake_onyx) -> None:
    run_id = store.begin_run("progress-publish")
    store.record_snapshot(run_id, "123", "detail", '{"data": {"id":123, "title": "Doc 123", "fullText": "Điều 1. X"}}', "hash1")
    store.record_status(StatusObservation(
        vbpl_id="123",
        eff_status="Còn hiệu lực",
        eff_from="2024-01-01",
        checked_at=datetime.now(UTC),
        content_hash="hash1",
        run_id=run_id,
    ))
    store.finish_run(run_id, "completed", 1.0)
    events: list[str] = []

    summary = Publisher(store, fake_onyx, progress=events.append).publish(run_id)

    assert events[0] == "publish: preparing 1 documents"
    assert "publish: upserted 1/1 documents" in events
    assert events[-1] == (
        f"publish: completed; upserted={summary.upserted_count} deleted={summary.deleted_count}"
    )

def test_deleted_instrument_removal(store, fake_onyx) -> None:
    run1 = store.begin_run("run-1")
    store.record_snapshot(run1, "123", "detail", '{"data": {"id":123, "title": "Doc 123", "fullText": "Điều 1. X"}}', "hash1")
    store.record_snapshot(run1, "124", "detail", '{"data": {"id":124, "title": "Doc 124", "fullText": "Điều 1. Y"}}', "hash2")
    store.record_status(StatusObservation(
        vbpl_id="123", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash1", run_id=run1
    ))
    store.record_status(StatusObservation(
        vbpl_id="124", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash2", run_id=run1
    ))
    store.finish_run(run1, "completed", 1.0)
    
    Publisher(store, fake_onyx).publish(run1)
    assert len(fake_onyx.upserted) == 2
    
    run2 = store.begin_run("run-2")
    store.record_snapshot(run2, "123", "detail", '{"data": {"id":123, "title": "Doc 123", "fullText": "Điều 1. X"}}', "hash1")
    store.record_status(StatusObservation(
        vbpl_id="123", eff_status="Còn hiệu lực", eff_from="2024-01-01", checked_at=datetime.now(UTC), content_hash="hash1", run_id=run2
    ))
    store.finish_run(run2, "completed", 1.0)
    
    fake_onyx.upserted.clear()
    fake_onyx.deleted.clear()
    
    Publisher(store, fake_onyx).publish(run2)
    assert len(fake_onyx.upserted) == 1
    assert fake_onyx.upserted[0].document_id == "vbpl:123"
    assert fake_onyx.deleted == ["vbpl:124"]
