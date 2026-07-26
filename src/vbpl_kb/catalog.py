import hashlib
import json
from typing import Any
from vbpl_kb.models import CatalogEntry, CatalogChangeSet


def _normalize_string(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, dict) and "name" in val:
        val = val["name"]
    val_str = str(val).strip()
    return val_str if val_str else None


def compute_catalog_fingerprint(payload: dict[str, Any]) -> str:
    vbpl_id = str(payload.get("id") if "id" in payload else payload.get("vbpl_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    doc_num = _normalize_string(payload.get("docNum") if "docNum" in payload else payload.get("doc_num"))
    doc_type = _normalize_string(payload.get("docType") if "docType" in payload else payload.get("doc_type"))
    updated_date = _normalize_string(payload.get("updatedDate") if "updatedDate" in payload else payload.get("updated_date"))
    eff_status = _normalize_string(payload.get("effStatus") if "effStatus" in payload else payload.get("eff_status"))
    eff_to = _normalize_string(payload.get("effTo") if "effTo" in payload else payload.get("eff_to"))

    canonical_dict = {
        "doc_num": doc_num,
        "doc_type": doc_type,
        "eff_status": eff_status,
        "eff_to": eff_to,
        "id": vbpl_id,
        "title": title,
        "updated_date": updated_date,
    }
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def parse_catalog_entry(payload: dict[str, Any]) -> CatalogEntry:
    vbpl_id = str(payload.get("id") if "id" in payload else payload.get("vbpl_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    doc_num = _normalize_string(payload.get("docNum") if "docNum" in payload else payload.get("doc_num"))
    doc_type = _normalize_string(payload.get("docType") if "docType" in payload else payload.get("doc_type"))
    updated_date = _normalize_string(payload.get("updatedDate") if "updatedDate" in payload else payload.get("updated_date"))
    eff_status = _normalize_string(payload.get("effStatus") if "effStatus" in payload else payload.get("eff_status"))
    eff_to = _normalize_string(payload.get("effTo") if "effTo" in payload else payload.get("eff_to"))
    
    fingerprint = compute_catalog_fingerprint(payload)

    return CatalogEntry(
        vbpl_id=vbpl_id,
        title=title,
        doc_num=doc_num,
        doc_type=doc_type,
        updated_date=updated_date,
        eff_status=eff_status,
        eff_to=eff_to,
        fingerprint=fingerprint,
        raw_payload=payload,
    )


def classify_catalog_changes(
    baseline: dict[str, CatalogEntry],
    current: dict[str, CatalogEntry],
) -> CatalogChangeSet:
    new_entries: list[CatalogEntry] = []
    changed_entries: list[CatalogEntry] = []
    unchanged_entries: list[CatalogEntry] = []
    absent_ids: list[str] = []

    for vbpl_id, entry in current.items():
        if vbpl_id not in baseline:
            new_entries.append(entry)
        else:
            baseline_entry = baseline[vbpl_id]
            if entry.fingerprint != baseline_entry.fingerprint:
                changed_entries.append(entry)
            else:
                unchanged_entries.append(entry)

    for vbpl_id in baseline:
        if vbpl_id not in current:
            absent_ids.append(vbpl_id)

    return CatalogChangeSet(
        new_entries=tuple(new_entries),
        changed_entries=tuple(changed_entries),
        unchanged_entries=tuple(unchanged_entries),
        absent_ids=tuple(absent_ids),
    )
