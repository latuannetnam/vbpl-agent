from typing import Any, Callable

class EvaluationReport:
    def __init__(self, current_law_safety_failures: int, passed: bool, metrics: dict[str, Any]):
        self.current_law_safety_failures = current_law_safety_failures
        self.passed = passed
        self.metrics = metrics

def evaluate_retrieval(
    cases: list[dict[str, Any]],
    search: Callable[[str], list[dict[str, Any]]]
) -> EvaluationReport:
    safety_failures = 0
    correct_citations = 0
    total_cases = len(cases)
    
    for case in cases:
        query = case["query"]
        expected_id = case["expected_vbpl_id"]
        expected_prov = case["expected_provision_key"]
        req_current = case.get("requires_current_status", False)
        
        results = search(query)
        matched_in_top_10 = None
        
        for res in results[:10]:
            if str(res.get("vbpl_id")) == str(expected_id) and res.get("provision_key") == expected_prov:
                matched_in_top_10 = res
                break
                
        if matched_in_top_10:
            correct_citations += 1
            if req_current and not matched_in_top_10.get("status_fresh", True):
                safety_failures += 1
        elif req_current:
            # If it requires current status and we didn't retrieve it at all,
            # that's also a safety failure
            safety_failures += 1
            
    recall_top_10 = correct_citations / total_cases if total_cases > 0 else 1.0
    passed = (safety_failures == 0) and (recall_top_10 >= 0.95)
    
    metrics = {
        "recall_top_10": recall_top_10,
        "total_cases": total_cases,
        "correct_citations": correct_citations
    }
    
    return EvaluationReport(
        current_law_safety_failures=safety_failures,
        passed=passed,
        metrics=metrics
    )
