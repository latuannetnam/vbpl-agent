from typing import Any

from vbpl_kb.catalog import (
    compute_catalog_fingerprint,
    parse_catalog_entry,
    classify_catalog_changes,
)
from vbpl_kb.models import CatalogEntry, DeltaManifest


def test_fingerprint_equality_despite_key_order() -> None:
    payload_a: dict[str, Any] = {
        "id": "12345",
        "title": "Nghị định 10/2026/NĐ-CP",
        "docNum": "10/2026/NĐ-CP",
        "docType": "Nghị định",
        "updatedDate": "2026-07-01",
        "effStatus": "Còn hiệu lực",
        "effTo": None,
    }
    payload_b: dict[str, Any] = {
        "effTo": None,
        "effStatus": "Còn hiệu lực",
        "updatedDate": "2026-07-01",
        "docType": "Nghị định",
        "docNum": "10/2026/NĐ-CP",
        "title": "Nghị định 10/2026/NĐ-CP",
        "id": "12345",
    }
    
    fp_a = compute_catalog_fingerprint(payload_a)
    fp_b = compute_catalog_fingerprint(payload_b)
    
    assert fp_a == fp_b
    assert len(fp_a) == 64  # SHA-256 hex digest


def test_classify_new_entry() -> None:
    raw_new = {
        "id": "101",
        "title": "Luật Mới 2026",
        "docNum": "01/2026/QH15",
        "docType": "Luật",
        "updatedDate": "2026-07-15",
        "effStatus": "Còn hiệu lực",
        "effTo": None,
    }
    new_entry = parse_catalog_entry(raw_new)
    
    baseline: dict[str, CatalogEntry] = {}
    current = {"101": new_entry}
    
    change_set = classify_catalog_changes(baseline, current)
    
    assert len(change_set.new_entries) == 1
    assert change_set.new_entries[0].vbpl_id == "101"
    assert len(change_set.changed_entries) == 0
    assert len(change_set.unchanged_entries) == 0
    assert len(change_set.absent_ids) == 0


def test_classify_changed_entry() -> None:
    raw_old = {
        "id": "102",
        "title": "Nghị định Cũ",
        "docNum": "02/2025/NĐ-CP",
        "docType": "Nghị định",
        "updatedDate": "2025-01-01",
        "effStatus": "Còn hiệu lực",
        "effTo": None,
    }
    old_entry = parse_catalog_entry(raw_old)
    baseline = {"102": old_entry}
    
    # Title and status updated
    raw_updated = dict(raw_old)
    raw_updated["effStatus"] = "Hết hiệu lực"
    raw_updated["updatedDate"] = "2026-07-20"
    updated_entry = parse_catalog_entry(raw_updated)
    current = {"102": updated_entry}
    
    change_set = classify_catalog_changes(baseline, current)
    
    assert len(change_set.new_entries) == 0
    assert len(change_set.changed_entries) == 1
    assert change_set.changed_entries[0].vbpl_id == "102"
    assert len(change_set.unchanged_entries) == 0


def test_classify_unchanged_entry() -> None:
    raw = {
        "id": "103",
        "title": "Thông tư Giữ Nguyên",
        "docNum": "03/2025/TT-BTC",
        "docType": "Thông tư",
        "updatedDate": "2025-03-01",
        "effStatus": "Còn hiệu lực",
        "effTo": None,
    }
    entry_1 = parse_catalog_entry(raw)
    entry_2 = parse_catalog_entry(raw)
    
    baseline = {"103": entry_1}
    current = {"103": entry_2}
    
    change_set = classify_catalog_changes(baseline, current)
    
    assert len(change_set.new_entries) == 0
    assert len(change_set.changed_entries) == 0
    assert len(change_set.unchanged_entries) == 1
    assert change_set.unchanged_entries[0].vbpl_id == "103"


def test_classify_absent_entries_as_candidates() -> None:
    raw_1 = {"id": "104", "title": "Doc 104"}
    raw_2 = {"id": "105", "title": "Doc 105"}
    
    baseline = {
        "104": parse_catalog_entry(raw_1),
        "105": parse_catalog_entry(raw_2),
    }
    # Current scan only found 104, 105 is missing
    current = {
        "104": parse_catalog_entry(raw_1),
    }
    
    change_set = classify_catalog_changes(baseline, current)
    
    assert "105" in change_set.absent_ids
    assert len(change_set.absent_ids) == 1


def test_delta_manifest_contract() -> None:
    delta = DeltaManifest(
        release_id="rel_20260726_001",
        parent_release_id="rel_20260725_001",
        created_at="2026-07-26T00:00:00Z",
        upsert_ids=["101", "102"],
        tombstone_ids=["105"],
        checksum_sha256="abc123hash",
    )
    assert delta.release_id == "rel_20260726_001"
    assert delta.upsert_ids == ["101", "102"]
    assert delta.tombstone_ids == ["105"]
