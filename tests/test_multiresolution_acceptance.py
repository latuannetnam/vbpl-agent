from datetime import datetime, timezone

from vbpl_kb.canonicalize import canonicalize_instrument
from vbpl_kb.legal_semantics import classify_authority, build_applicability, resolve_relations
from vbpl_kb.legal_tree import LegalNodeDraft
from vbpl_kb.projection import CanonicalBundle, project_current, project_history, project_evidence


def test_acceptance_multi_view_retrieval_routing() -> None:
    detail_data = {
        "id": 88001,
        "title": "Nghị định số 88/2026/NĐ-CP về Bảo hiểm y tế",
        "docNum": "88/2026/NĐ-CP",
        "issueDate": "2026-05-01",
        "effDate": "2026-06-01",
        "effStatus": {"name": "Còn hiệu lực"},
    }
    draft = canonicalize_instrument(detail_data, "payload_hash_88", "evidence_hash_88")
    nodes = [
        LegalNodeDraft(
            node_type="article",
            display_label="Điều 5",
            normalized_coordinate="dieu-05",
            heading="Mức hưởng bảo hiểm y tế đối với thân nhân người có công",
            sibling_ordinal=1,
            materialized_path="dieu-05",
            text="Điều 5. Mức hưởng bảo hiểm y tế cho con liệt sĩ là 100%...",
            lead_in_text=None,
            source_anchor="dieu-05",
            source_start=0,
            source_end=50,
            content_hash="hash_node_5",
            parse_status="verified_structured",
        )
    ]
    auth = classify_authority("Nghị định", "Chính phủ")
    app = build_applicability("Còn hiệu lực", verified_at=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc))
    rels = resolve_relations(draft.version_id, None, [])

    bundle = CanonicalBundle(
        draft=draft,
        nodes=nodes,
        authority=auth,
        applicability=app,
        relations=rels,
    )

    # 1. Current View query
    cur_docs = list(project_current(bundle, now=datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)))
    assert len(cur_docs) > 0
    cur_text = cur_docs[0].sections[0].text
    assert "con liệt sĩ" in cur_text
    assert "Mức hưởng" in cur_text

    # 2. History View query
    hist_docs = list(project_history(bundle))
    assert len(hist_docs) > 0
    assert hist_docs[0].metadata["corpus_view"] == "history"

    # 3. Evidence View query
    ev_docs = list(project_evidence(bundle))
    assert len(ev_docs) > 0
    assert ev_docs[0].metadata["corpus_view"] == "evidence"
    assert "evidence_hash_88" in ev_docs[0].sections[0].text


def test_acceptance_refusal_when_unverified() -> None:
    refusal_text = "Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này."
    assert "Không tìm thấy căn cứ VBPL" in refusal_text
