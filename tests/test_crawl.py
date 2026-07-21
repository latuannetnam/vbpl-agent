from typing import Any
import pytest
from vbpl_kb.state import StateStore
from vbpl_kb.crawl import DailyCrawler

class FakeVBPLClient:
    def __init__(self):
        self.catalog_pages = [[]]
        self.fail_detail_ids = set()

    def list_catalog_page(self, page_number: int, page_size: int):
        if page_number <= len(self.catalog_pages):
            return [{"id": int(i)} for i in self.catalog_pages[page_number - 1]]
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

