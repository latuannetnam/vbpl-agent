import re
from typing import Any
from vbpl_kb.models import StatusObservation, OnyxDocument

def normalize_instrument(raw: dict[str, Any], status: StatusObservation, revision: str) -> OnyxDocument:
    vbpl_id = str(raw.get("id") or status.vbpl_id)
    title = raw.get("title") or f"Document {vbpl_id}"
    full_text = raw.get("fullText") or ""
    
    canonical_link = f"https://vbpl.vn/doc/{vbpl_id}"
    status_checked_at_iso = status.checked_at.isoformat()
    
    provenance = (
        f"Document ID: vbpl:{vbpl_id}\n"
        f"Title: {title}\n"
        f"Link: {canonical_link}\n"
        f"Status: {status.eff_status}\n"
        f"Verification Time: {status_checked_at_iso}\n"
        f"Corpus Revision: {revision}\n\n"
    )
    
    has_articles = bool(re.search(r"^\s*Điều \d+", full_text, re.MULTILINE))
    
    if has_articles:
        body = re.sub(r"^\s*(Điều \d+[\.\s]*)", r"## \1", full_text, flags=re.MULTILINE)
        citation_structure = "parsed"
    else:
        body = f"## Toàn văn\n\n{full_text}"
        citation_structure = "unparsed"
        
    content = provenance + body
    
    metadata = {
        "legal_status": status.eff_status,
        "status_checked_at": status_checked_at_iso,
        "effective_from": status.eff_from or "",
        "source_url": canonical_link,
        "corpus_revision": revision,
        "document_type": raw.get("documentType", ""),
        "legal_area": raw.get("legalArea", ""),
        "issuer": raw.get("issuer", ""),
        "scope": raw.get("scope", ""),
        "citation_structure": citation_structure
    }
    
    return OnyxDocument(
        document_id=f"vbpl:{vbpl_id}",
        content=content,
        link=canonical_link,
        metadata=metadata
    )
