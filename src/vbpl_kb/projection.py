from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Literal, Sequence
from vbpl_kb.canonicalize import CanonicalInstrumentDraft
from vbpl_kb.legal_semantics import (
    AuthorityClassificationResult,
    ApplicabilityEnvelopeDraft,
    LegalRelationDraft,
)
from vbpl_kb.legal_tree import LegalNodeDraft
from vbpl_kb.models import OnyxDocument, OnyxSection
from vbpl_kb.projection_ids import (
    build_current_article_id,
    build_current_atomic_id,
    build_current_relation_id,
    build_evidence_doc_id,
    build_history_article_id,
    build_history_atomic_id,
)

CorpusView = Literal["current", "history", "evidence"]
ProjectionKind = Literal["article", "atomic", "relation", "evidence"]


@dataclass(frozen=True)
class CanonicalBundle:
    draft: CanonicalInstrumentDraft
    nodes: Sequence[LegalNodeDraft]
    authority: AuthorityClassificationResult
    applicability: ApplicabilityEnvelopeDraft
    relations: Sequence[LegalRelationDraft]


def _build_compact_header(
    bundle: CanonicalBundle,
    breadcrumb: str,
    relation_tokens: str = "",
) -> str:
    draft = bundle.draft
    auth = bundle.authority
    app = bundle.applicability

    verified_str = app.verified_at.strftime("%Y-%m-%d %H:%M:%S UTC") if app.verified_at else "N/A"
    eff_from_str = str(app.effective_from) if app.effective_from else "N/A"
    eff_to_str = str(app.effective_to) if app.effective_to else "N/A"

    lines = [
        f"Văn bản: {draft.title} | Số: {draft.number or 'N/A'}",
        f"Hình thức/Cơ quan: {auth.form} | {auth.issuer}",
        f"Thẩm quyền: {auth.order_string} | {auth.statutory_group}",
        f"Vị trí: {breadcrumb}",
        f"Trạng thái/Xác minh: {app.status} | {verified_str}",
        f"Hiệu lực/Phạm vi: {eff_from_str}..{eff_to_str} | {app.jurisdiction}",
    ]
    if relation_tokens:
        lines.append(f"Quan hệ đã xác minh: {relation_tokens}")

    return "\n".join(lines)


def _build_common_metadata(
    bundle: CanonicalBundle,
    corpus_view: CorpusView,
    projection_kind: ProjectionKind,
    materialized_path: str = "",
) -> dict[str, str | list[str]]:
    draft = bundle.draft
    auth = bundle.authority
    app = bundle.applicability

    meta: dict[str, str | list[str]] = {
        "corpus_view": corpus_view,
        "projection_kind": projection_kind,
        "instrument_id": draft.instrument_id,
        "official_source_id": draft.official_source_id,
        "title": draft.title,
        "number": draft.number or "",
        "form": auth.form,
        "issuer": auth.issuer,
        "statutory_group": auth.statutory_group,
        "order_string": auth.order_string,
        "status": app.status,
        "verified_at": app.verified_at.isoformat() if app.verified_at else "",
        "jurisdiction": app.jurisdiction,
        "version_id": draft.version_id,
    }

    if materialized_path:
        meta["logical_provision_id"] = f"{draft.instrument_id}:{materialized_path}"
        meta["materialized_path"] = materialized_path

    if app.subject_tokens:
        meta["subject_tokens"] = [str(t) for t in app.subject_tokens]

    return meta


def project_current(bundle: CanonicalBundle, now: datetime) -> Iterator[OnyxDocument]:
    if not bundle.applicability.is_current_eligible:
        return

    draft = bundle.draft
    official_id = draft.official_source_id
    url = f"https://vbpl.vn/van-ban/chi-tiet/--{official_id}"

    # Group nodes by article for Article context docs
    article_nodes: list[LegalNodeDraft] = [n for n in bundle.nodes if n.node_type == "article"]
    leaf_nodes: list[LegalNodeDraft] = [n for n in bundle.nodes if n.node_type in ("point", "clause", "article")]

    for art in article_nodes:
        doc_id = build_current_article_id(official_id, art.materialized_path)
        header = _build_compact_header(bundle, breadcrumb=art.display_label)
        body = f"{header}\n\n{art.text}"

        meta = _build_common_metadata(bundle, "current", "article", art.materialized_path)
        section = OnyxSection(section_id=doc_id, text=body, link=url)

        yield OnyxDocument(
            document_id=doc_id,
            sections=(section,),
            link=url,
            metadata=meta,
        )

    for leaf in leaf_nodes:
        # Atomic leaves
        doc_id = build_current_atomic_id(official_id, leaf.materialized_path)
        header = _build_compact_header(bundle, breadcrumb=leaf.materialized_path)
        body = f"{header}\n\n{leaf.text}"

        meta = _build_common_metadata(bundle, "current", "atomic", leaf.materialized_path)
        section = OnyxSection(section_id=doc_id, text=body, link=url)

        yield OnyxDocument(
            document_id=doc_id,
            sections=(section,),
            link=url,
            metadata=meta,
        )

    for rel in bundle.relations:
        doc_id = build_current_relation_id(official_id, rel.logical_edge_id)
        header = _build_compact_header(bundle, breadcrumb=f"Quan hệ: {rel.relation_type}")
        body = f"{header}\n\nLoại quan hệ: {rel.relation_type}\nTrích dẫn: {rel.quote or 'N/A'}"

        meta = _build_common_metadata(bundle, "current", "relation")
        meta["relation_type"] = rel.relation_type
        meta["logical_edge_id"] = rel.logical_edge_id

        section = OnyxSection(section_id=doc_id, text=body, link=url)
        yield OnyxDocument(
            document_id=doc_id,
            sections=(section,),
            link=url,
            metadata=meta,
        )


def project_history(bundle: CanonicalBundle) -> Iterator[OnyxDocument]:
    draft = bundle.draft
    official_id = draft.official_source_id
    version_hash = draft.version_id
    url = f"https://vbpl.vn/van-ban/chi-tiet/--{official_id}"

    for node in bundle.nodes:
        if node.node_type == "article":
            doc_id = build_history_article_id(official_id, version_hash, node.materialized_path)
            kind: ProjectionKind = "article"
        else:
            doc_id = build_history_atomic_id(official_id, version_hash, node.materialized_path)
            kind = "atomic"

        header = _build_compact_header(bundle, breadcrumb=node.materialized_path)
        body = f"{header}\n\n{node.text}"

        meta = _build_common_metadata(bundle, "history", kind, node.materialized_path)
        section = OnyxSection(section_id=doc_id, text=body, link=url)

        yield OnyxDocument(
            document_id=doc_id,
            sections=(section,),
            link=url,
            metadata=meta,
        )


def project_evidence(bundle: CanonicalBundle) -> Iterator[OnyxDocument]:
    draft = bundle.draft
    official_id = draft.official_source_id
    ev_hash = draft.raw_evidence_hash
    url = f"https://vbpl.vn/van-ban/chi-tiet/--{official_id}"

    doc_id = build_evidence_doc_id(official_id, "detail", ev_hash)
    header = _build_compact_header(bundle, breadcrumb="Bằng chứng chính thức")
    body = f"{header}\n\nHash SHA-256 evidence: {ev_hash}\nPayload hash: {draft.detail_payload_hash}"

    meta = _build_common_metadata(bundle, "evidence", "evidence")
    meta["raw_evidence_hash"] = ev_hash
    meta["detail_payload_hash"] = draft.detail_payload_hash

    section = OnyxSection(section_id=doc_id, text=body, link=url)
    yield OnyxDocument(
        document_id=doc_id,
        sections=(section,),
        link=url,
        metadata=meta,
    )
