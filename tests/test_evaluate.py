from vbpl_kb.evaluate import evaluate_retrieval, evaluate_authority_bundles


def test_evaluation_rejects_stale_current_law_result() -> None:
    report = evaluate_retrieval(
        [{"query": "Q", "expected_vbpl_id": "1", "expected_provision_key": "dieu-1",
          "requires_current_status": True}],
        lambda _: [{"vbpl_id": "1", "provision_key": "dieu-1", "status_fresh": False}]
    )
    assert report.current_law_safety_failures == 1
    assert report.passed is False


def test_current_law_answer_requires_fresh_verified_status() -> None:
    report = evaluate_retrieval(
        [{"id": "unknown-status", "query": "Q", "expected_vbpl_id": "123", "expected_provision_key": "Điều 1", "expected": {"requires_current_law_refusal": True}}],
        lambda _: [{"vbpl_id": "123", "status_fresh": False, "provision_key": "Điều 1"}],
    )
    assert report.passed is False
    assert report.current_law_safety_failures == 1


def test_bundle_metrics_enforce_all_design_gates() -> None:
    report = evaluate_authority_bundles(
        cases=[{
            "case_id": "bundle",
            "expected_document_ids": ["vbpl:law", "vbpl:decree"],
            "expected_controlling_id": "vbpl:law",
            "expected_conflict_outcome": "resolved",
        }],
        results=[{
            "case_id": "bundle",
            "document_ids": ["vbpl:law", "vbpl:decree"],
            "current_law_safe": True,
            "conflict_outcome": "resolved",
        }],
        baseline_chunk_count=100,
        candidate_chunk_count=120,
    )
    assert report.metrics["controlling_provision_recall_at_10"] == 1.0
    assert report.metrics["authority_bundle_completeness_at_10"] == 1.0
    assert report.metrics["chunk_count_ratio"] == 1.2
    assert report.passed is True


def test_chunk_growth_over_125_percent_blocks_acceptance() -> None:
    report = evaluate_authority_bundles(
        cases=[], results=[], baseline_chunk_count=100, candidate_chunk_count=126
    )
    assert report.passed is False
