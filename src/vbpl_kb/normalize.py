import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from typing import Any

from vbpl_kb.models import StatusObservation, OnyxDocument, OnyxSection, Provision
from vbpl_kb.authority import classify_authority, AuthorityClassification
from vbpl_kb.applicability import build_applicability, ApplicabilityEnvelope
from vbpl_kb.provisions import split_provisions


class _HTMLText(HTMLParser):
    _break_tags = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._break_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._break_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    text = unescape("".join(parser.parts)).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _slug(value: str) -> str:
    value = value.lower().replace("đ", "d")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-")


def _content(raw: dict[str, Any]) -> str:
    document_content = raw.get("documentContent")
    if isinstance(document_content, dict) and isinstance(document_content.get("content"), str):
        return _html_to_text(document_content["content"])
    if isinstance(raw.get("fullText"), str):
        return raw["fullText"]
    return ""


def normalize_legal_status(raw_status: str | None) -> str:
    value = (raw_status or "").casefold()
    if "hết hiệu lực một phần" in value:
        return "partially_repealed"
    if "còn hiệu lực" in value:
        return "in_force"
    if "hết hiệu lực" in value or "bãi bỏ" in value:
        return "repealed"
    if "ngưng hiệu lực" in value or "tạm ngừng" in value:
        return "suspended"
    if "chưa có hiệu lực" in value:
        return "not_yet_effective"
    return "unknown"


def render_context_header(
    *,
    title: str,
    document_number: str,
    provision: Provision,
    authority: AuthorityClassification,
    applicability: ApplicabilityEnvelope,
    relation_tokens: tuple[str, ...] = (),
) -> str:
    order = (
        str(authority.article4_order)
        if authority.article4_order is not None
        else "unknown"
    )
    relations = ", ".join(relation_tokens) if relation_tokens else "none"
    return "\n".join((
        f"Văn bản: {title}",
        f"Số hiệu: {document_number}",
        f"Vị trí: {provision.provision_key}",
        f"Hình thức: {authority.normative_form}",
        f"Cơ quan: {authority.issuer_type}",
        f"Thẩm quyền Điều 4: {order}",
        f"Trạng thái: {applicability.legal_status_normalized}",
        f"Xác minh: {applicability.verified_at}",
        f"Hiệu lực: {applicability.effective_from} -> {applicability.effective_to}",
        f"Phạm vi: {applicability.jurisdiction_level}:{applicability.jurisdiction_name}",
        f"Quan hệ đã xác minh: {relations}",
    ))


def normalize_instrument(
    raw: dict[str, Any],
    status: StatusObservation,
    revision: str,
    relation_tokens: tuple[str, ...] = (),
) -> OnyxDocument:
    vbpl_id = str(raw.get("id") or status.vbpl_id)
    doc_num = str(raw.get("docNum") or raw.get("document_number") or "")
    title = str(raw.get("title") or f"Document {vbpl_id}")
    full_text = _content(raw)

    doc_type = raw.get("docType") or raw.get("document_type") or raw.get("normative_form") or ""
    issuer = raw.get("agencyName") or raw.get("issuer") or ""

    authority = classify_authority(doc_type, issuer)
    applicability = build_applicability(raw, status, authority, revision)
    parsed_provisions = split_provisions(full_text)

    canonical_link = f"https://vbpl.vn/van-ban/chi-tiet/{_slug(title)}--{vbpl_id}"

    sections: list[OnyxSection] = []
    citation_structures: set[str] = set()

    for prov in parsed_provisions:
        citation_structures.add(prov.citation_structure)
        header = render_context_header(
            title=title,
            document_number=doc_num,
            provision=prov,
            authority=authority,
            applicability=applicability,
            relation_tokens=relation_tokens,
        )
        sec_text = f"{header}\n\n{prov.text}"
        sections.append(
            OnyxSection(
                section_id=prov.provision_key,
                text=sec_text,
                link=canonical_link,
            )
        )

    cit_struct = "parsed" if "parsed" in citation_structures else "unparsed"

    metadata: dict[str, Any] = {
        "hierarchy_regime": authority.hierarchy_regime,
        "article4_order": str(authority.article4_order) if authority.article4_order is not None else "unknown",
        "normative_form": authority.normative_form,
        "authority_group": authority.authority_group,
        "issuer_type": authority.issuer_type,
        "classification_status": authority.classification_status,
        "classification_source": authority.classification_source,
        "classification_version": authority.classification_version,
        "is_normative": str(authority.is_normative),
        "legal_status_raw": applicability.legal_status_raw,
        "legal_status_normalized": applicability.legal_status_normalized,
        "verified_at": applicability.verified_at,
        "status_source": applicability.status_source,
        "effective_from": applicability.effective_from,
        "effective_to": applicability.effective_to,
        "jurisdiction_level": applicability.jurisdiction_level,
        "jurisdiction_code": applicability.jurisdiction_code,
        "jurisdiction_name": applicability.jurisdiction_name,
        "transitional_until": applicability.transitional_until,
        "source_url": applicability.source_url,
        "corpus_revision": applicability.corpus_revision,
        "status_evidence_hash": applicability.status_evidence_hash,
        "citation_structure": cit_struct,
        "document_number": doc_num,
        "title": title,
        "relation_tokens": list(relation_tokens),
    }

    return OnyxDocument(
        projection_schema_version=2,
        document_id=f"vbpl:{vbpl_id}",
        sections=tuple(sections),
        link=canonical_link,
        metadata=metadata,
    )
