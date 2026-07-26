import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from vbpl_kb.canonicalize import canonicalize_instrument, CanonicalInstrumentDraft
from vbpl_kb.db_models import Base, Instrument, InstrumentVersion, LegalNode
from vbpl_kb.evidence import EvidenceStore
from vbpl_kb.legal_tree import parse_legal_tree, LegalNodeDraft
from vbpl_kb.repositories import CanonicalRepository, EvidenceRepository

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "vbpl"


@pytest.fixture
def memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_parse_legal_tree_structured_hierarchical_paths() -> None:
    detail_raw = (FIXTURES_DIR / "structured-document.json").read_bytes()
    html_raw = (FIXTURES_DIR / "structured-document.html").read_bytes()
    detail_data = json.loads(detail_raw)["data"]

    nodes = parse_legal_tree(detail_data, html_raw)
    paths = [n.materialized_path for n in nodes]

    assert "phan-02" in paths
    assert "phan-02/chuong-03" in paths
    assert "phan-02/chuong-03/dieu-12" in paths
    assert "phan-02/chuong-03/dieu-12/khoan-01" in paths
    assert "phan-02/chuong-03/dieu-12/khoan-01/diem-a" in paths

    point_a = next(n for n in nodes if n.materialized_path == "phan-02/chuong-03/dieu-12/khoan-01/diem-a")
    assert point_a.node_type == "point"
    assert point_a.normalized_coordinate == "diem-a"
    assert point_a.display_label == "Điểm a"
    assert "Tờ khai thuế theo mẫu quy định" in point_a.text
    assert point_a.parse_status == "verified_structured"


def test_canonicalize_instrument_produces_stable_identities() -> None:
    detail_data = {
        "id": 12345,
        "title": "Luật Quản lý thuế",
        "docNum": "38/2019/QH14",
        "issueDate": "2019-06-13",
        "effDate": "2020-07-01",
        "effStatus": {"name": "Còn hiệu lực"},
    }
    raw_payload_hash = "hash_payload_123"
    raw_evidence_hash = "hash_evidence_456"

    draft = canonicalize_instrument(
        detail_data,
        detail_payload_hash=raw_payload_hash,
        raw_evidence_hash=raw_evidence_hash,
    )

    assert draft.instrument_id == "vbpl:12345"
    assert draft.version_id.startswith("ver:")
    assert draft.title == "Luật Quản lý thuế"
    assert draft.number == "38/2019/QH14"


def test_canonical_repository_upsert_immutable_versions(tmp_path, memory_session) -> None:
    evidence_store = EvidenceStore(tmp_path)
    ev_obj = evidence_store.put(
        b"raw content",
        media_type="application/json",
        official_url="https://vbpl.vn/doc/12345",
        endpoint="detail",
        corpus_revision="rev-1",
    )
    ev_repo = EvidenceRepository(memory_session)
    ev_repo.persist_evidence_metadata(ev_obj)

    detail_data = {
        "id": 12345,
        "title": "Luật Quản lý thuế",
        "docNum": "38/2019/QH14",
        "effStatus": {"name": "Còn hiệu lực"},
    }

    draft1 = canonicalize_instrument(detail_data, "hash_payload_1", ev_obj.hash_sha256)
    nodes1 = [
        LegalNodeDraft(
            node_type="article",
            display_label="Điều 1",
            normalized_coordinate="dieu-01",
            heading="Phạm vi điều chỉnh",
            sibling_ordinal=1,
            materialized_path="dieu-01",
            text="Điều 1. Phạm vi điều chỉnh",
            lead_in_text=None,
            source_anchor="dieu-01",
            source_start=0,
            source_end=25,
            content_hash="hash_node_1",
            parse_status="verified_structured",
        )
    ]

    repo = CanonicalRepository(memory_session)
    res1 = repo.upsert_observation(draft1, nodes1)
    assert res1.is_new_version is True
    assert res1.instrument_id == "vbpl:12345"

    # Same draft -> reuses version
    res2 = repo.upsert_observation(draft1, nodes1)
    assert res2.is_new_version is False
    assert res2.version_id == res1.version_id
