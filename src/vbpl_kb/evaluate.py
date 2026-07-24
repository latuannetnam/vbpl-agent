from typing import Any, Callable
from pydantic import BaseModel, ConfigDict


class EvaluationReport:
    def __init__(self, current_law_safety_failures: int, passed: bool, metrics: dict[str, Any]):
        self.current_law_safety_failures = current_law_safety_failures
        self.passed = passed
        self.metrics = metrics


class AuthorityBundleReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    passed: bool
    safety_failures: int
    metrics: dict[str, float]
    cases: list[dict[str, Any]] = []


def evaluate_retrieval(
    cases: list[dict[str, Any]],
    search: Callable[[str], list[dict[str, Any]]],
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
        "correct_citations": correct_citations,
    }

    return EvaluationReport(
        current_law_safety_failures=safety_failures,
        passed=passed,
        metrics=metrics,
    )


def evaluate_authority_bundles(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    baseline_chunk_count: int,
    candidate_chunk_count: int,
) -> AuthorityBundleReport:
    safety_failures = 0
    total_cases = len(cases)
    result_by_id = {r["case_id"]: r for r in results if "case_id" in r}

    controlling_correct = 0
    controlling_total = 0
    bundle_recalled = 0
    bundle_total = 0
    conflict_correct = 0
    conflict_total = 0
    unresolved_correct = 0
    unresolved_total = 0

    for case in cases:
        cid = case["case_id"]
        res = result_by_id.get(cid, {})

        if not res.get("current_law_safe", True):
            safety_failures += 1

        res_docs = res.get("document_ids", [])[:10]

        # Controlling provision recall
        expected_controlling = case.get("expected_controlling_id")
        if expected_controlling:
            controlling_total += 1
            if expected_controlling in res_docs:
                controlling_correct += 1

        # Bundle completeness
        expected_docs = case.get("expected_document_ids", [])
        if expected_docs:
            for ed in expected_docs:
                bundle_total += 1
                if ed in res_docs:
                    bundle_recalled += 1

        # Conflict outcome
        exp_conflict = case.get("expected_conflict_outcome")
        if exp_conflict:
            conflict_total += 1
            if res.get("conflict_outcome") == exp_conflict:
                conflict_correct += 1

        # Unresolved
        if exp_conflict == "unresolved":
            unresolved_total += 1
            if res.get("conflict_outcome") == "unresolved":
                unresolved_correct += 1

    controlling_recall = controlling_correct / controlling_total if controlling_total > 0 else 1.0
    bundle_completeness = bundle_recalled / bundle_total if bundle_total > 0 else 1.0
    conflict_accuracy = conflict_correct / conflict_total if conflict_total > 0 else 1.0
    unresolved_accuracy = unresolved_correct / unresolved_total if unresolved_total > 0 else 1.0

    chunk_ratio = (
        candidate_chunk_count / baseline_chunk_count
        if baseline_chunk_count > 0
        else 999.0
    )

    passed = (
        safety_failures == 0
        and conflict_accuracy == 1.0
        and unresolved_accuracy == 1.0
        and controlling_recall >= 0.95
        and bundle_completeness >= 0.90
        and chunk_ratio <= 1.25
    )

    metrics: dict[str, float] = {
        "controlling_provision_recall_at_10": controlling_recall,
        "authority_bundle_completeness_at_10": bundle_completeness,
        "conflict_accuracy": conflict_accuracy,
        "unresolved_accuracy": unresolved_accuracy,
        "chunk_count_ratio": round(chunk_ratio, 4),
        "total_cases": float(total_cases),
    }

    return AuthorityBundleReport(
        passed=passed,
        safety_failures=safety_failures,
        metrics=metrics,
        cases=cases,
    )
