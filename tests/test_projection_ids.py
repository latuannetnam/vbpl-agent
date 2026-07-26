from vbpl_kb.projection_ids import (
    build_current_article_id,
    build_current_atomic_id,
    build_current_relation_id,
    build_history_article_id,
    build_history_atomic_id,
    build_history_relation_id,
    build_evidence_doc_id,
)


def test_projection_id_namespaces() -> None:
    official_id = "12345"
    path = "phan-01/chuong-02/dieu-10"
    version_hash = "abc123ver"
    edge_hash = "edge456"
    ev_hash = "ev789"

    cur_art = build_current_article_id(official_id, path)
    cur_atom = build_current_atomic_id(official_id, path)
    cur_rel = build_current_relation_id(official_id, edge_hash)

    hist_art = build_history_article_id(official_id, version_hash, path)
    hist_atom = build_history_atomic_id(official_id, version_hash, path)
    hist_rel = build_history_relation_id(official_id, version_hash, edge_hash)

    ev_doc = build_evidence_doc_id(official_id, "detail", ev_hash)

    assert cur_art.startswith(f"vbpl:{official_id}:current:article:")
    assert cur_atom.startswith(f"vbpl:{official_id}:current:atomic:")
    assert cur_rel.startswith(f"vbpl:{official_id}:current:relation:")

    assert hist_art.startswith(f"vbpl:{official_id}:history:{version_hash}:article:")
    assert hist_atom.startswith(f"vbpl:{official_id}:history:{version_hash}:atomic:")
    assert hist_rel.startswith(f"vbpl:{official_id}:history:{version_hash}:relation:")

    assert ev_doc == f"vbpl:{official_id}:evidence:detail:{ev_hash}"

    # IDs must be disjoint
    all_ids = {cur_art, cur_atom, cur_rel, hist_art, hist_atom, hist_rel, ev_doc}
    assert len(all_ids) == 7
