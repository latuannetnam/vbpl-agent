from typing import Any
import pytest
from vbpl_kb.state import StateStore
from vbpl_kb.crawl import DailyCrawler

class FakeVBPLClient:
    def __init__(self):
        self.catalog_pages = [[]]
        self.fail_detail_ids = set()
        self.fail_catalog_pages = set()
        self.catalog_calls = []
        self.canonical_pages: dict[str, str] = {}

    def list_catalog_page(self, page_number: int, page_size: int):
        self.catalog_calls.append(page_number)
        if page_number in self.fail_catalog_pages:
            raise RuntimeError(f"catalog page {page_number} failed")
        if page_number <= len(self.catalog_pages):
            res = []
            for i in self.catalog_pages[page_number - 1]:
                if isinstance(i, dict):
                    res.append(i)
                else:
                    res.append({
                        "id": int(i),
                        "title": f"Document {i}",
                        "docNum": f"{i}/2026/NĐ-CP",
                        "docType": "Nghị định",
                        "updatedDate": "2026-07-01",
                        "effStatus": {"name": "Còn hiệu lực"},
                        "effTo": None,
                    })
            return res
        return []

    def get_detail(self, vbpl_id: str):
        if vbpl_id in self.fail_detail_ids:
            raise Exception("Failed to fetch detail")
        from vbpl_kb.vbpl_client import VBPLDetail
        import json
        raw_data: dict[str, Any] = {
            "id": int(vbpl_id),
            "title": f"Document {vbpl_id}",
            "effStatus": {"name": "Còn hiệu lực"},
            "effFrom": "2024-01-01"
        }
        return VBPLDetail(
            vbpl_id=vbpl_id,
            title=raw_data["title"],
            eff_status=raw_data["effStatus"]["name"],
            eff_from=raw_data["effFrom"],
            raw_json=json.dumps({"data": raw_data}),
            raw_data=raw_data
        )

    def get_canonical_page(self, vbpl_id: str) -> str:
        return self.canonical_pages[vbpl_id]

@pytest.fixture
def fake_client():
    return FakeVBPLClient()

@pytest.fixture
def store(tmp_path):
    return StateStore.open(tmp_path / "state.sqlite3")

def test_crawl_continues_and_records_coverage(fake_client, store) -> None:
    fake_client.catalog_pages = [["1", "2", "3"]]
    fake_client.fail_detail_ids = {"2"}
    summary = DailyCrawler(fake_client, store).run("vbpl-2026-07-21")
    assert (summary.detail_count, summary.failed_ids, summary.coverage) == (2, ["2"], 2 / 3)

def test_crawl_checkpoint_restart(fake_client, store) -> None:
    fake_client.catalog_pages = [["1", "2"]]
    fake_client.fail_detail_ids = {"2"}
    summary1 = DailyCrawler(fake_client, store).run("vbpl-2026-07-21")
    assert (summary1.detail_count, summary1.failed_ids) == (1, ["2"])

    fake_client.fail_detail_ids = set()
    called_ids = []
    original_get_detail = fake_client.get_detail
    def spy_get_detail(vbpl_id):
        called_ids.append(vbpl_id)
        return original_get_detail(vbpl_id)
    fake_client.get_detail = spy_get_detail

    summary2 = DailyCrawler(fake_client, store).run("vbpl-2026-07-21")
    assert (summary2.detail_count, summary2.failed_ids) == (2, [])
    assert called_ids == ["2"]


def test_crawl_reports_catalog_and_fetch_progress(fake_client, store) -> None:
    fake_client.catalog_pages = [["1", "2"]]
    events: list[str] = []

    DailyCrawler(fake_client, store, progress=events.append).run("progress-crawl")

    assert events[0] == "crawl: catalog page 1 discovered; documents=2"
    assert "crawl: fetched 2/2 documents (failed=0)" in events
    assert events[-1] == "crawl: completed; documents=2/2 (failed=0)"


def test_crawl_reports_failed_detail_id_and_reason(fake_client, store) -> None:
    fake_client.catalog_pages = [["1", "2"]]
    fake_client.fail_detail_ids = {"2"}
    events: list[str] = []

    DailyCrawler(fake_client, store, progress=events.append).run("failed-detail")

    assert "crawl: failed 2 (Exception: Failed to fetch detail)" in events


def test_crawl_uses_verified_canonical_fallback_for_missing_status(fake_client, store) -> None:
    fake_client.catalog_pages = [["1"]]
    original = fake_client.get_detail

    def missing_status(vbpl_id):
        detail = original(vbpl_id)
        detail.eff_status = None
        return detail

    fake_client.get_detail = missing_status
    fake_client.canonical_pages["1"] = '<script type="application/ld+json">{"@type":"Legislation","name":"Quyết định 1","legislationLegalForce":"InForce"}</script>'

    summary = DailyCrawler(fake_client, store).run("canonical-fallback")

    assert summary.coverage == 1.0
    assert store.latest_status("1").eff_status == "Còn hiệu lực"


def test_catalog_failure_is_partial_and_never_reports_full_coverage(fake_client, store) -> None:
    def fail_catalog(page_number: int, page_size: int):
        raise RuntimeError("gateway unavailable")

    fake_client.list_catalog_page = fail_catalog

    summary = DailyCrawler(fake_client, store).run("vbpl-2026-07-22")

    assert summary.coverage == 0.0
    assert summary.catalog_complete is False
    assert store.get_run("vbpl-2026-07-22").status == "partial"


def test_catalog_checkpoint_resumes_after_the_last_saved_page(fake_client, store) -> None:
    fake_client.catalog_pages = [["1"], ["2"]]
    fake_client.fail_catalog_pages = {2}

    first = DailyCrawler(fake_client, store).run("resume-catalog")
    assert first.catalog_complete is False
    assert fake_client.catalog_calls == [1, 2]

    fake_client.fail_catalog_pages.clear()
    fake_client.catalog_calls.clear()
    second = DailyCrawler(fake_client, store).run("resume-catalog")

    assert second.catalog_complete is True
    assert second.detail_count == 2
    assert fake_client.catalog_calls == [2, 3]


def test_incremental_crawl_only_fetches_new_or_changed_details(fake_client, store) -> None:
    # Run 1: docs 1 and 2 with explicit catalog fields
    doc1 = {"id": 1, "title": "Document 1", "docNum": "1/2026", "effStatus": "Còn hiệu lực"}
    doc2 = {"id": 2, "title": "Document 2 Original", "docNum": "2/2026", "effStatus": "Còn hiệu lực"}
    fake_client.catalog_pages = [[doc1, doc2]]
    summary1 = DailyCrawler(fake_client, store).run("run-1")
    assert summary1.catalog_complete is True
    assert summary1.detail_count == 2
    assert summary1.fetched_detail_count == 2

    # Track detail calls for run 2
    fetched_ids = []
    original_get_detail = fake_client.get_detail
    def spy_get_detail(vbpl_id):
        fetched_ids.append(vbpl_id)
        return original_get_detail(vbpl_id)
    fake_client.get_detail = spy_get_detail

    # Run 2: doc 1 unchanged, doc 2 changed title, doc 3 is new
    doc2_changed = {"id": 2, "title": "Document 2 Updated Title", "docNum": "2/2026", "effStatus": "Còn hiệu lực"}
    doc3_new = {"id": 3, "title": "Document 3 New", "docNum": "3/2026", "effStatus": "Còn hiệu lực"}

    fake_client.catalog_pages = [[doc1, doc2_changed, doc3_new]]

    summary2 = DailyCrawler(fake_client, store).run("run-2")
    assert summary2.catalog_complete is True
    assert summary2.detail_count == 3
    assert summary2.fetched_detail_count == 2
    assert set(fetched_ids) == {"2", "3"}  # 1 was unchanged and not re-fetched!


def test_incomplete_scan_produces_no_tombstones(fake_client, store) -> None:
    # Run 1: baseline has 1, 2
    fake_client.catalog_pages = [["1", "2"]]
    summary1 = DailyCrawler(fake_client, store).run("run-1")
    assert summary1.catalog_complete is True

    # Run 2: catalog fails on page 1
    fake_client.fail_catalog_pages = {1}
    summary2 = DailyCrawler(fake_client, store).run("run-2")
    assert summary2.catalog_complete is False
    assert summary2.tombstone_ids == []
    assert store.get_tombstone_ids() == []

