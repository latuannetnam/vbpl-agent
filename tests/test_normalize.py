import pytest
from datetime import datetime, UTC
from vbpl_kb.models import StatusObservation
from vbpl_kb.normalize import normalize_instrument

@pytest.fixture
def raw_instrument():
    return {
        "id": 123,
        "title": "Nghị định số 12/2024/NĐ-CP",
        "fullText": "Điều 8. Quy định chung\nNội dung Điều 8...\nĐiều 9. Hiệu lực thi hành\nNội dung Điều 9...",
        "effFrom": "2024-01-01"
    }

@pytest.fixture
def status():
    return StatusObservation(
        vbpl_id="123",
        eff_status="Còn hiệu lực",
        eff_from="2024-01-01",
        checked_at=datetime(2026, 7, 21, tzinfo=UTC),
        content_hash="hash123",
        run_id="vbpl-2026-07-21"
    )

def test_projection_contains_citable_provenance(raw_instrument, status) -> None:
    document = normalize_instrument(raw_instrument, status, "vbpl-2026-07-21")
    assert document.document_id == "vbpl:123"
    assert "Status: Còn hiệu lực" in document.content
    assert "## Điều 8." in document.content
    assert document.metadata["status_checked_at"] == "2026-07-21T00:00:00+00:00"

def test_unparsed_citation_structure(status) -> None:
    raw = {"id": 123, "title": "X", "fullText": "Không có điều khoản nào rõ ràng."}
    doc = normalize_instrument(raw, status, "vbpl-2026-07-21")
    assert doc.metadata["citation_structure"] == "unparsed"
    assert "## Toàn văn" in doc.content

def test_partial_effect_status(raw_instrument, status) -> None:
    partial_status = StatusObservation(
        vbpl_id=status.vbpl_id,
        eff_status="Hết hiệu lực một phần",
        eff_from=status.eff_from,
        checked_at=status.checked_at,
        content_hash=status.content_hash,
        run_id=status.run_id
    )
    doc = normalize_instrument(raw_instrument, partial_status, "vbpl-2026-07-21")
    assert doc.metadata["legal_status"] == "Hết hiệu lực một phần"
    assert "Status: Hết hiệu lực một phần" in doc.content

