from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from typing import Any, Mapping
from vbpl_kb.legal_tree import LegalNodeDraft


@dataclass(frozen=True)
class CanonicalInstrumentDraft:
    instrument_id: str
    official_source_id: str
    title: str
    number: str | None
    issue_date: date | None
    effective_date: date | None
    current_status: str | None
    detail_payload_hash: str
    normalized_content_hash: str
    raw_evidence_hash: str
    version_id: str


def parse_iso_date(val: Any) -> date | None:
    if isinstance(val, str) and val.strip():
        try:
            return datetime.strptime(val.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def canonicalize_instrument(
    detail: Mapping[str, Any],
    detail_payload_hash: str,
    raw_evidence_hash: str,
) -> CanonicalInstrumentDraft:
    official_source_id = str(detail.get("id") or detail.get("vbpl_id") or "")
    if not official_source_id:
        raise ValueError("Missing official source ID in detail")

    title = str(detail.get("title") or "")
    number = detail.get("docNum") or detail.get("doc_num")
    number = str(number) if number is not None else None

    issue_date = parse_iso_date(detail.get("issueDate") or detail.get("issue_date"))
    effective_date = parse_iso_date(detail.get("effDate") or detail.get("effective_date"))

    eff_status = detail.get("effStatus")
    if isinstance(eff_status, dict):
        status_name = str(eff_status.get("name") or "")
    elif isinstance(eff_status, str):
        status_name = eff_status
    else:
        status_name = None

    instrument_id = f"vbpl:{official_source_id}"

    # Calculate normalized content hash over canonical fields and text
    norm_bytes = f"{instrument_id}\0{title}\0{number}\0{status_name}".encode("utf-8")
    normalized_content_hash = hashlib.sha256(norm_bytes).hexdigest()

    version_id = "ver:" + hashlib.sha256(
        f"{instrument_id}\0{detail_payload_hash}\0{normalized_content_hash}".encode("utf-8")
    ).hexdigest()

    return CanonicalInstrumentDraft(
        instrument_id=instrument_id,
        official_source_id=official_source_id,
        title=title,
        number=number,
        issue_date=issue_date,
        effective_date=effective_date,
        current_status=status_name,
        detail_payload_hash=detail_payload_hash,
        normalized_content_hash=normalized_content_hash,
        raw_evidence_hash=raw_evidence_hash,
        version_id=version_id,
    )


def compute_node_id(version_id: str, node_type: str, materialized_path: str) -> str:
    return "node:" + hashlib.sha256(
        f"{version_id}\0{node_type}\0{materialized_path}".encode("utf-8")
    ).hexdigest()
