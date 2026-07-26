import json
import re
import hashlib
from dataclasses import dataclass
from typing import Any
from vbpl_kb.models import LegalReference


class RawReferenceCandidate:
    def __init__(
        self,
        from_vbpl_id: str,
        from_provision_key: str,
        doc_type: str,
        doc_number: str,
        to_provision_key: str | None,
        relation_type: str,
        source_quote: str,
        source_offset: int | None = None,
    ):
        self.from_vbpl_id = from_vbpl_id
        self.from_provision_key = from_provision_key
        self.doc_type = doc_type
        self.doc_number = doc_number
        self.to_provision_key = to_provision_key
        self.relation_type = relation_type
        self.source_quote = source_quote
        self.source_offset = source_offset


@dataclass(frozen=True)
class VerifiedReferenceType:
    relation_type: str
    evidence_url: str
    evidence_label: str
    example_source_id: str
    example_target_id: str


VERIFIED_REFERENCE_TYPES: dict[int, VerifiedReferenceType] = {
    3: VerifiedReferenceType(
        relation_type="legal_basis",
        evidence_url="https://vbpl.vn/TW/Pages/vbpq-vanbanlienquan.aspx?ItemID=178717",
        evidence_label="Văn bản căn cứ",
        example_source_id="178717",
        example_target_id="32801",
    ),
    10: VerifiedReferenceType(
        relation_type="amends",
        evidence_url="https://vbpl.vn/TW/Pages/vbpq-vanbanlienquan.aspx?ItemID=178717",
        evidence_label="Văn bản bị sửa đổi",
        example_source_id="178717",
        example_target_id="175440",
    ),
}


def remove_vietnamese_accents(text: str) -> str:
    text = text.lower()
    text = text.replace("đ", "d")
    text = re.sub(r"[aàáạảãâầấậẩẫăằắặẳẵ]", "a", text)
    text = re.sub(r"[eèéẹẻẽêềếệểễ]", "e", text)
    text = re.sub(r"[iìíịỉĩ]", "i", text)
    text = re.sub(r"[oòóọỏõôồốộổỗơờớợởỡ]", "o", text)
    text = re.sub(r"[uùúụủũưừứựửữ]", "u", text)
    text = re.sub(r"[yỳýỵỷỹ]", "y", text)
    return text


def normalize_signature(doc_type: str, doc_number: str) -> str:
    type_slug = remove_vietnamese_accents(doc_type).strip().replace(" ", "-")
    num_slug = remove_vietnamese_accents(doc_number).strip().strip(".")
    return f"{type_slug}:{num_slug}"


def extract_references(from_vbpl_id: str, from_provision_key: str, text: str) -> list[RawReferenceCandidate]:
    candidates: list[RawReferenceCandidate] = []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)

    doc_types = ["Nghị định", "Luật", "Thông tư", "Quyết định", "Nghị quyết", "Hiến pháp", "Sắc lệnh", "Pháp lệnh", "Chỉ thị"]
    doc_types_regex = "|".join(doc_types)
    doc_pattern = re.compile(
        r"\b(" + doc_types_regex + r")\s+(?:số\s+)?([0-9]+[\w\-\/\.]*)",
        re.IGNORECASE,
    )
    provision_pattern = re.compile(r"(Điều|Khoản|Điểm)\s+(\d+)", re.IGNORECASE)

    current_offset = 0
    for sentence in sentences:
        sentence_str = sentence.strip()
        if not sentence_str:
            current_offset += len(sentence)
            continue

        doc_matches = list(doc_pattern.finditer(sentence_str))
        if doc_matches:
            sentence_lower = sentence_str.lower()
            relation_type = "cites"
            if "bãi bỏ" in sentence_lower or "hủy bỏ" in sentence_lower:
                relation_type = "repeals"
            elif "thay thế" in sentence_lower:
                relation_type = "replaces"
            elif "sửa đổi" in sentence_lower:
                relation_type = "amends"
            elif "bổ sung" in sentence_lower:
                relation_type = "supplements"
            elif "căn cứ" in sentence_lower:
                relation_type = "legal_basis"
            elif "hướng dẫn" in sentence_lower:
                relation_type = "guides_implementation"

            for match in doc_matches:
                doc_type = match.group(1)
                doc_number = match.group(2).rstrip(".,)")

                to_provision_key = None
                prov_match = provision_pattern.search(sentence_str)
                if prov_match:
                    prov_type = prov_match.group(1).lower()
                    prov_name = (
                        "dieu"
                        if "điều" in remove_vietnamese_accents(prov_type)
                        else "khoan" if "khoan" in remove_vietnamese_accents(prov_type) else "diem"
                    )
                    to_provision_key = f"{prov_name}-{prov_match.group(2)}"

                candidates.append(
                    RawReferenceCandidate(
                        from_vbpl_id=from_vbpl_id,
                        from_provision_key=from_provision_key,
                        doc_type=doc_type,
                        doc_number=doc_number,
                        to_provision_key=to_provision_key,
                        relation_type=relation_type,
                        source_quote=sentence_str,
                        source_offset=current_offset + match.start(),
                    )
                )

        current_offset += len(sentence)

    return candidates


def normalize_relationships(
    from_vbpl_id: str,
    structured: list[dict[str, Any]],
    candidates: list[RawReferenceCandidate],
    instrument_index: dict[str, str],
    corpus_revision: str,
) -> tuple[LegalReference, ...]:
    edges: list[LegalReference] = []

    # Sort structured items for deterministic processing
    sorted_structured = sorted(
        structured,
        key=lambda item: (
            item.get("referenceType", 0),
            str((item.get("targetDocument") or {}).get("id", "")),
        ),
    )

    for item in sorted_structured:
        ref_type = item.get("referenceType")
        target_doc = item.get("targetDocument") or {}
        target_id_raw = target_doc.get("id")
        target_id = str(target_id_raw) if target_id_raw is not None else None
        target_num = target_doc.get("docNum") or target_id or ""

        ev_bytes = json.dumps(item, sort_keys=True).encode("utf-8")
        ev_hash = hashlib.sha256(ev_bytes).hexdigest()

        if ref_type in VERIFIED_REFERENCE_TYPES:
            verified_info = VERIFIED_REFERENCE_TYPES[ref_type]
            rel_type = verified_info.relation_type
            res_state = "verified"
            searchable = (target_id != from_vbpl_id) and (target_id is not None)
            ev_ref = verified_info.evidence_url
        else:
            rel_type = "unknown"
            res_state = "unmapped"
            searchable = False
            ev_ref = f"official_structured:referenceType={ref_type}"

        edges.append(
            LegalReference(
                from_vbpl_id=from_vbpl_id,
                from_provision_key="whole",
                to_vbpl_id=target_id,
                to_provision_key=None,
                relation_type=rel_type,  # type: ignore[arg-type]
                evidence_kind="official_structured",
                evidence_reference=ev_ref,
                source_quote=f"Official reference {target_num}",
                source_offset=None,
                resolution_state=res_state,  # type: ignore[arg-type]
                evidence_hash=ev_hash,
                corpus_revision=corpus_revision,
                searchable=searchable,
            )
        )

    for cand in candidates:
        sig = normalize_signature(cand.doc_type, cand.doc_number)
        to_vbpl_id = instrument_index.get(sig)

        ev_hash = hashlib.sha256(cand.source_quote.encode("utf-8")).hexdigest()
        is_self = (to_vbpl_id == from_vbpl_id)

        edges.append(
            LegalReference(
                from_vbpl_id=from_vbpl_id,
                from_provision_key=cand.from_provision_key,
                to_vbpl_id=to_vbpl_id,
                to_provision_key=cand.to_provision_key,
                relation_type="unknown",
                evidence_kind="text_candidate",
                evidence_reference=f"text_candidate:{sig}",
                source_quote=cand.source_quote,
                source_offset=cand.source_offset,
                resolution_state="candidate" if to_vbpl_id else "unresolved",
                evidence_hash=ev_hash,
                corpus_revision=corpus_revision,
                searchable=False if is_self else False,  # text candidates are never searchable legal effects
            )
        )

    # Deduplicate
    seen: set[tuple[str, str | None, str | None, str | None, str, str]] = set()
    unique_edges: list[LegalReference] = []

    for edge in edges:
        dedup_key = (
            edge.from_vbpl_id,
            edge.from_provision_key,
            edge.to_vbpl_id,
            edge.to_provision_key,
            edge.relation_type,
            edge.evidence_kind,
        )
        if dedup_key not in seen:
            seen.add(dedup_key)
            unique_edges.append(edge)

    return tuple(unique_edges)


def relationship_tokens(references: tuple[LegalReference, ...] | list[LegalReference]) -> tuple[str, ...]:
    tokens = {
        f"{edge.relation_type}:{edge.to_vbpl_id}"
        for edge in references
        if edge.searchable
        and edge.to_vbpl_id is not None
        and edge.resolution_state in {"verified", "resolved_citation"}
        and edge.relation_type != "unknown"
    }
    return tuple(sorted(tokens))


def extract_structured_references(from_vbpl_id: str, raw: dict[str, Any]) -> list[LegalReference]:
    structured_raw = raw.get("references") or []
    return list(
        normalize_relationships(
            from_vbpl_id=from_vbpl_id,
            structured=structured_raw,
            candidates=[],
            instrument_index={},
            corpus_revision="raw",
        )
    )


def resolve_reference(candidate: RawReferenceCandidate, instrument_index: dict[str, str]) -> LegalReference:
    sig = normalize_signature(candidate.doc_type, candidate.doc_number)
    to_vbpl_id = instrument_index.get(sig)
    ev_hash = hashlib.sha256(candidate.source_quote.encode("utf-8")).hexdigest()
    return LegalReference(
        from_vbpl_id=candidate.from_vbpl_id,
        from_provision_key=candidate.from_provision_key,
        to_vbpl_id=to_vbpl_id,
        to_provision_key=candidate.to_provision_key,
        relation_type="unknown",
        evidence_kind="text_candidate",
        evidence_reference=f"text_candidate:{sig}",
        source_quote=candidate.source_quote,
        source_offset=candidate.source_offset,
        resolution_state="candidate" if to_vbpl_id else "unresolved",
        evidence_hash=ev_hash,
        corpus_revision="legacy",
        searchable=False,
    )


def append_related_documents_section(content: str, references: list[LegalReference], store: Any = None) -> str:
    resolved_refs = [r for r in references if r.to_vbpl_id is not None]
    if not resolved_refs:
        return content

    lines = ["", "## Văn bản liên quan", ""]
    for ref in resolved_refs:
        target_id = ref.to_vbpl_id
        target_status = "Chưa rõ"
        if target_id and store is not None and hasattr(store, "latest_status"):
            status_obs = store.latest_status(target_id)
            if status_obs:
                target_status = status_obs.eff_status

        canonical_link = f"https://vbpl.vn/doc/{target_id}"

        line = (
            f"- Tài liệu liên quan: vbpl:{target_id} | "
            f"Trạng thái: {target_status} | "
            f"Liên kết: {canonical_link} | "
            f"Điều khoản nguồn: {ref.from_provision_key} | "
            f"Loại quan hệ: {ref.relation_type}"
        )
        lines.append(line)

    return content + "\n".join(lines)
