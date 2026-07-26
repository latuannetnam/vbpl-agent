from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from vbpl_kb.crawl import DailyCrawler
from vbpl_kb.evidence import EvidenceStore
from vbpl_kb.db_models import Base
from vbpl_kb.repositories import CatalogRepository
from vbpl_kb.vbpl_client import VBPLDetail


@pytest.fixture
def memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_daily_crawler_retains_evidence_and_scans(tmp_path, memory_session) -> None:
    mock_client = MagicMock()
    mock_client.settings.vbpl_gateway_url = "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public"
    mock_client.settings.max_pages = None
    # Page 1 returns 1 item, Page 2 returns empty list
    mock_client.list_catalog_page_with_raw.side_effect = [
        (
            b'{"data": [{"id": 101, "title": "Doc 101", "effStatus": {"name": "Con hieu luc"}}]}',
            [{"id": 101, "title": "Doc 101", "effStatus": {"name": "Con hieu luc"}}],
        ),
        (b'{"data": []}', []),
    ]
    # Detail
    mock_client.get_detail_with_raw.return_value = (
        b'{"data": {"id": 101, "title": "Doc 101", "effStatus": {"name": "Con hieu luc"}}}',
        VBPLDetail(
            vbpl_id="101",
            title="Doc 101",
            eff_status="Con hieu luc",
            eff_from="2025-01-01",
            raw_json='{"data": {"id": 101, "title": "Doc 101"}}',
            raw_data={"id": 101, "title": "Doc 101"},
        ),
    )

    catalog_repo = CatalogRepository(memory_session)
    evidence_store = EvidenceStore(tmp_path)

    crawler = DailyCrawler(
        client=mock_client,
        catalog=catalog_repo,
        evidence=evidence_store,
        session=memory_session,
        progress=print,
    )

    summary = crawler.run("rev-2026-07-26")

    assert summary.failed_ids == []
    assert summary.catalog_complete is True
    assert 101 in summary.changed_or_new_ids
    assert len(list((tmp_path / "sha256").rglob("*"))) > 0
