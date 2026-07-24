import pytest
from datetime import datetime, UTC
from vbpl_kb.provisions import split_provisions
from vbpl_kb.models import StatusObservation
from vbpl_kb.normalize import normalize_instrument


def test_split_provisions_is_ordered_and_preserves_nested_amended_text() -> None:
    sections = split_provisions(
        "Điều 1. Sửa đổi\n"
        "1. Sửa đổi Điều 4 như sau:\n"
        "“Điều 4. Hệ thống văn bản\n"
        "1. Hiến pháp.\n"
        "2. Bộ luật, luật.\n"
        "Điều 2. Thi hành\n"
        "Nội dung."
    )
    assert [section.provision_key for section in sections] == [
        "dieu-1",
        "dieu-1/khoan-1",
        "dieu-1/khoan-1/noi-dung-sua-doi/dieu-4",
        "dieu-1/khoan-1/noi-dung-sua-doi/dieu-4/khoan-1",
        "dieu-1/khoan-1/noi-dung-sua-doi/dieu-4/khoan-2",
        "dieu-2",
    ]


def test_each_retrievable_section_repeats_compact_legal_context() -> None:
    status = StatusObservation(
        vbpl_id="178717",
        eff_status="Còn hiệu lực",
        eff_from="2025-07-01T00:00:00",
        checked_at=datetime(2026, 7, 24, 8, 0, 0, tzinfo=UTC),
        content_hash="a" * 64,
        run_id="vbpl-2026-07-24",
        status_source="api",
    )
    doc = normalize_instrument(
        {
            "id": "178717",
            "docType": {"name": "Luật", "parentCode": "VBQPPL"},
            "docNum": "87/2025/QH15",
            "title": "Luật 87/2025/QH15",
            "agencyName": "Quốc hội",
            "fullText": "Điều 1. Nội dung\n1. Khoản một.",
            "effFrom": "2025-07-01T00:00:00",
        },
        status,
        "vbpl-2026-07-24",
    )
    assert doc.projection_schema_version == 2
    assert doc.sections[1].section_id == "dieu-1/khoan-1"
    assert "Văn bản: Luật 87/2025/QH15" in doc.sections[1].text
    assert "Thẩm quyền Điều 4: 2" in doc.sections[1].text
    assert f"Xác minh: {status.checked_at.isoformat()}" in doc.sections[1].text
