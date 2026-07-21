import pytest
from datetime import datetime, UTC
from vbpl_kb.state import StateStore
from vbpl_kb.models import StatusObservation, LegalReference
from vbpl_kb.references import extract_references, resolve_reference, append_related_documents_section

@pytest.fixture
def instrument_index():
    # Maps unique document signatures to target VBPL IDs
    return {
        "nghi-dinh:12/2024/nd-cp": "B"
    }

@pytest.fixture
def store(tmp_path):
    return StateStore.open(tmp_path / "state.sqlite3")

def test_explicit_repeal_keeps_evidence(instrument_index) -> None:
    candidates = extract_references("A", "dieu-1", "Bãi bỏ Điều 8 Nghị định số 12/2024/NĐ-CP.")
    assert len(candidates) > 0
    edge = resolve_reference(candidates[0], instrument_index)
    assert (edge.relation_type, edge.to_vbpl_id) == ("repeals", "B")
    assert "Bãi bỏ" in edge.source_quote

def test_ambiguous_reference_is_not_guessed(instrument_index) -> None:
    candidates = extract_references("A", "dieu-1", "Theo Nghị định số 12.")
    assert len(candidates) > 0
    edge = resolve_reference(candidates[0], instrument_index)
    assert edge.to_vbpl_id is None
    assert edge.relation_type == "unknown"

def test_related_documents_section_formatting(store) -> None:
    status_b = StatusObservation(
        vbpl_id="B",
        eff_status="Hết hiệu lực một phần",
        eff_from="2024-01-01",
        checked_at=datetime(2026, 7, 21, tzinfo=UTC),
        content_hash="hash-b",
        run_id="run-1"
    )
    store.record_status(status_b)
    
    ref = LegalReference(
        from_vbpl_id="A",
        from_provision_key="dieu-1",
        to_vbpl_id="B",
        to_provision_key=None,
        relation_type="cites",
        source_quote="Theo quy định tại Nghị định B."
    )
    
    content = "## Điều 1\nNội dung Điều 1..."
    updated_content = append_related_documents_section(content, [ref], store)
    
    assert "## Văn bản liên quan" in updated_content
    assert "vbpl:B" in updated_content
    assert "Hết hiệu lực một phần" in updated_content
    assert "cites" in updated_content

