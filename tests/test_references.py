from vbpl_kb.references import (
    extract_references,
    normalize_relationships,
    relationship_tokens,
    extract_structured_references,
)


def test_verified_structured_codes_keep_evidence_and_deduplicate() -> None:
    edges = normalize_relationships(
        from_vbpl_id="178717",
        structured=[
            {"id": "a", "referenceType": 3, "targetDocument": {"id": "32801", "docNum": "Không số"}},
            {"id": "b", "referenceType": 10, "targetDocument": {"id": "175440", "docNum": "64/2025/QH15"}},
            {"id": "c", "referenceType": 10, "targetDocument": {"id": "175440", "docNum": "64/2025/QH15"}},
        ],
        candidates=[],
        instrument_index={},
        corpus_revision="run-1",
    )
    assert [(edge.relation_type, edge.to_vbpl_id) for edge in edges] == [
        ("legal_basis", "32801"),
        ("amends", "175440"),
    ]
    assert all(edge.evidence_kind == "official_structured" for edge in edges)
    assert all(len(edge.evidence_hash) == 64 for edge in edges)


def test_unmapped_structured_code_remains_unknown() -> None:
    edge = normalize_relationships(
        "A",
        [{"referenceType": 999, "targetDocument": {"id": "B", "docNum": "B/2026"}}],
        [],
        {},
        "run-1",
    )[0]
    assert edge.relation_type == "unknown"
    assert edge.resolution_state == "unmapped"


def test_text_amendment_verb_is_candidate_not_legal_effect() -> None:
    candidate = extract_references("A", "dieu-1", "Sửa đổi Luật số 64/2025/QH15.")[0]
    edge = normalize_relationships(
        "A", [], [candidate], {"luat:64/2025/qh15": "B"}, "run-1"
    )[0]
    assert edge.relation_type == "unknown"
    assert edge.evidence_kind == "text_candidate"
    assert edge.resolution_state == "candidate"
    assert relationship_tokens((edge,)) == ()


def test_heuristic_self_edge_is_not_searchable() -> None:
    candidate = extract_references("178717", "dieu-1", "Luật số 87/2025/QH15.")[0]
    edge = normalize_relationships(
        "178717", [], [candidate], {"luat:87/2025/qh15": "178717"}, "run-1"
    )[0]
    assert edge.searchable is False


def test_structured_vbpl_reference_uses_authoritative_target_id() -> None:
    edges = extract_structured_references(
        "187835",
        {
            "references": [{
                "targetDocument": {"id": "175258", "docNum": "63/2025/QH15"},
                "referenceType": 3,
                "referenceProvisions": None,
            }]
        },
    )

    assert edges[0].to_vbpl_id == "175258"
    assert edges[0].relation_type == "legal_basis"
