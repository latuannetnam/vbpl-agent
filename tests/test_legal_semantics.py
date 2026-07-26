from datetime import datetime, timezone
import pytest

from vbpl_kb.legal_semantics import (
    classify_authority,
    build_applicability,
    is_current_eligible,
    resolve_relations,
    EligibilityDecision,
    LegalRelationDraft,
)


def test_authority_regime_classification() -> None:
    classification = classify_authority(
        normative_form="Luật",
        issuer="Quốc hội",
        regime_id="2025-07-01",
    )
    assert classification.order_string == "02"
    assert classification.statutory_group == "Bộ luật, Luật, Nghị quyết của Quốc hội"
    assert classification.classification_version == "2025.1"


def test_is_current_eligible_fail_closed() -> None:
    now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

    # Valid in-force instrument
    decision_ok = is_current_eligible(
        status="Còn hiệu lực",
        verified_at=datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc),
        now=now,
        parse_status="verified_structured",
    )
    assert decision_ok.eligible is True
    assert len(decision_ok.exclusion_reasons) == 0

    # Stale observation (> 24h)
    decision_stale = is_current_eligible(
        status="Còn hiệu lực",
        verified_at=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
        now=now,
        parse_status="verified_structured",
    )
    assert decision_stale.eligible is False
    assert "stale_status" in decision_stale.exclusion_reasons

    # Repealed document
    decision_repealed = is_current_eligible(
        status="Hết hiệu lực toàn bộ",
        verified_at=datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc),
        now=now,
        parse_status="verified_structured",
    )
    assert decision_repealed.eligible is False
    assert "expired_or_repealed" in decision_repealed.exclusion_reasons


def test_resolve_relations_evidence_gating() -> None:
    relations = resolve_relations(
        source_version_id="ver:111",
        source_node_id="node:dieu-01",
        raw_references=[
            {
                "target_vbpl_id": "123",
                "relation_type": "amends",
                "evidence_kind": "official_structured",
                "evidence_hash": "hash_ev_1",
                "quote": "Sửa đổi Điều 4",
            },
            {
                "target_vbpl_id": "456",
                "relation_type": "cites",
                "evidence_kind": "text_candidate",
                "evidence_hash": "hash_ev_2",
                "quote": "Theo quy định tại khoản 2",
            },
        ],
    )

    assert len(relations) == 2
    amend_rel = next(r for r in relations if r.relation_type == "amends")
    assert amend_rel.is_verified_effect is True

    cite_rel = next(r for r in relations if r.relation_type == "cites")
    assert cite_rel.is_verified_effect is False
