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
    assert document.projection_schema_version == 2
    assert "Trạng thái: Còn hiệu lực" in document.content
    assert "Vị trí: dieu-8" in document.content
    assert document.metadata["verified_at"] == "2026-07-21T00:00:00+00:00"


def test_unparsed_citation_structure(status) -> None:
    raw = {"id": 123, "title": "X", "fullText": "Không có điều khoản nào rõ ràng."}
    doc = normalize_instrument(raw, status, "vbpl-2026-07-21")
    assert doc.metadata["citation_structure"] == "unparsed"
    assert doc.sections[0].section_id == "toan-van"
    assert "Không có điều khoản nào rõ ràng." in doc.content


def test_empty_full_text_creates_fallback_section(status) -> None:
    raw = {"id": 10001, "title": "Văn bản chưa có nội dung text", "fullText": ""}
    doc = normalize_instrument(raw, status, "vbpl-2026-07-21")
    assert len(doc.sections) == 1
    assert doc.sections[0].section_id == "toan-van"
    assert "Văn bản chưa có nội dung text" in doc.content


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
    assert doc.metadata["legal_status_normalized"] == "Hết hiệu lực một phần"
    assert "Trạng thái: Hết hiệu lực một phần" in doc.content


def test_projection_uses_real_vbpl_html_content_and_citable_subheadings(status) -> None:
    raw = {
        "id": 187835,
        "title": "Nghị định số 135/2026/NĐ-CP Quy định cơ chế",
        "docNum": "135/2026/NĐ-CP",
        "documentContent": {
            "content": "<p>Điều 1. Phạm vi điều chỉnh</p><p>1. Nội dung khoản một.</p><p>a) Nội dung điểm a.</p>"
        },
    }

    doc = normalize_instrument(raw, status, "vbpl-2026-07-21")

    assert doc.sections[0].section_id == "dieu-1"
    assert "Nội dung điểm a." in doc.content
    assert doc.link.endswith("--187835")


def test_normalize_instrument_emits_verified_status_and_article_headings() -> None:
    doc = normalize_instrument(
        {"id": "123", "title": "Nghị định số 12/2024/NĐ-CP", "fullText": "Điều 1. Nội dung"},
        StatusObservation(vbpl_id="123", eff_status="Còn hiệu lực", eff_from=None,
            checked_at=datetime(2026, 7, 22, tzinfo=UTC), content_hash="raw-sha",
            run_id="vbpl-2026-07-22", status_source="api"),
        "vbpl-2026-07-22",
    )
    assert doc.document_id == "vbpl:123"
    assert doc.sections[0].section_id == "dieu-1"
    assert doc.metadata["legal_status_normalized"] == "Còn hiệu lực"
    assert doc.metadata["verified_at"] == "2026-07-22T00:00:00+00:00"
