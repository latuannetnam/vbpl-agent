from vbpl_kb.evaluate import evaluate_retrieval

def test_evaluation_rejects_stale_current_law_result() -> None:
    report = evaluate_retrieval(
        [{"query": "Q", "expected_vbpl_id": "1", "expected_provision_key": "dieu-1",
          "requires_current_status": True}],
        lambda _: [{"vbpl_id": "1", "provision_key": "dieu-1", "status_fresh": False}]
    )
    assert report.current_law_safety_failures == 1
    assert report.passed is False
