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
        query = case.get("query", "")
        expected_id = case.get("expected_vbpl_id")
        expected_prov = case.get("expected_provision_key")
        expected_dict = case.get("expected", {})
        req_current = (
            case.get("requires_current_status", False)
            or expected_dict.get("requires_current_law_refusal", False)
        )
        
        results = search(query)
        matched_in_top_10 = None
        
        if expected_id and expected_prov:
            for res in results[:10]:
                if str(res.get("vbpl_id")) == str(expected_id) and res.get("provision_key") == expected_prov:
                    matched_in_top_10 = res
                    break
                
        if matched_in_top_10:
            correct_citations += 1
            status_fresh = matched_in_top_10.get("status_fresh", True)
            legal_status = matched_in_top_10.get("legal_status_normalized") or matched_in_top_10.get("status")
            if req_current and (not status_fresh or legal_status == "unknown"):
                safety_failures += 1
        elif req_current:
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
