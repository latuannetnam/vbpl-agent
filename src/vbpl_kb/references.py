import re
from vbpl_kb.models import LegalReference
from vbpl_kb.state import StateStore

class RawReferenceCandidate:
    def __init__(
        self,
        from_vbpl_id: str,
        from_provision_key: str,
        doc_type: str,
        doc_number: str,
        to_provision_key: str | None,
        relation_type: str,
        source_quote: str
    ):
        self.from_vbpl_id = from_vbpl_id
        self.from_provision_key = from_provision_key
        self.doc_type = doc_type
        self.doc_number = doc_number
        self.to_provision_key = to_provision_key
        self.relation_type = relation_type
        self.source_quote = source_quote

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
    
    # Split text into sentences/lines
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    
    doc_types = ["Nghị định", "Luật", "Thông tư", "Quyết định", "Nghị quyết", "Hiến pháp", "Sắc lệnh", "Pháp lệnh", "Chỉ thị"]
    doc_types_regex = "|".join(doc_types)
    doc_pattern = re.compile(
        r"\b(" + doc_types_regex + r")\s+(?:số\s+)?([0-9]+[\w\-\/\.]*)",
        re.IGNORECASE
    )
    
    provision_pattern = re.compile(r"(Điều|Khoản|Điểm)\s+(\d+)", re.IGNORECASE)
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        doc_matches = list(doc_pattern.finditer(sentence))
        if not doc_matches:
            continue
            
        # Check for relationship verbs
        sentence_lower = sentence.lower()
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
            
            # Look for provision in the same sentence
            to_provision_key = None
            prov_match = provision_pattern.search(sentence)
            if prov_match:
                prov_type = prov_match.group(1).lower()
                # Map to standard slug like 'dieu-8'
                # Let's map vietnamese words
                prov_name = "dieu" if "điều" in remove_vietnamese_accents(prov_type) else \
                            "khoan" if "khoan" in remove_vietnamese_accents(prov_type) else \
                            "diem"
                to_provision_key = f"{prov_name}-{prov_match.group(2)}"
                
            candidates.append(
                RawReferenceCandidate(
                    from_vbpl_id=from_vbpl_id,
                    from_provision_key=from_provision_key,
                    doc_type=doc_type,
                    doc_number=doc_number,
                    to_provision_key=to_provision_key,
                    relation_type=relation_type,
                    source_quote=sentence
                )
            )
            
    return candidates

def resolve_reference(candidate: RawReferenceCandidate, instrument_index: dict[str, str]) -> LegalReference:
    sig = normalize_signature(candidate.doc_type, candidate.doc_number)
    to_vbpl_id = instrument_index.get(sig)
    
    relation_type = candidate.relation_type
    if to_vbpl_id is None:
        relation_type = "unknown"
        
    return LegalReference(
        from_vbpl_id=candidate.from_vbpl_id,
        from_provision_key=candidate.from_provision_key,
        to_vbpl_id=to_vbpl_id,
        to_provision_key=candidate.to_provision_key,
        relation_type=relation_type,
        source_quote=candidate.source_quote
    )


def extract_structured_references(from_vbpl_id: str, raw: dict) -> list[LegalReference]:
    """Use VBPL's explicit target IDs before attempting text-based matching."""
    edges: list[LegalReference] = []
    for reference in raw.get("references") or []:
        target = reference.get("targetDocument") or {}
        target_id = target.get("id")
        if target_id is None:
            continue
        target_number = target.get("docNum") or str(target_id)
        edges.append(
            LegalReference(
                from_vbpl_id=from_vbpl_id,
                from_provision_key="whole",
                to_vbpl_id=str(target_id),
                to_provision_key=None,
                relation_type="cites",
                source_quote=f"VBPL structured reference: {target_number}",
            )
        )
    return edges

def append_related_documents_section(content: str, references: list[LegalReference], store: StateStore | None = None) -> str:
    resolved_refs = [r for r in references if r.to_vbpl_id is not None]
    if not resolved_refs:
        return content
        
    lines = ["", "## Văn bản liên quan", ""]
    for ref in resolved_refs:
        target_id = ref.to_vbpl_id
        target_status = "Chưa rõ"
        if target_id and store is not None:
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
