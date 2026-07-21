# Verified VBPL Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve malformed official VBPL records from their canonical page when explicitly verifiable, otherwise quarantine them without contaminating the active legal corpus.

**Architecture:** Add a small canonical-page resolver returning a typed verified result or quarantine reason. The crawler persists explicit resolutions and records quarantine outcomes. The publisher selects verified current-run documents and removes active projections whose current verification failed.

**Tech Stack:** Python 3.12, httpx, HTMLParser, SQLite, pytest/respx.

## Global Constraints

- Never infer legal status from workflow or boolean fields.
- Canonical-page fallback is attempted only when primary API title/status is missing.
- Only explicit title and legal-effect labels are publishable.
- Logs contain IDs and reasons, never secrets or response bodies.
- A quarantined record is excluded, not permitted to block verified-record promotion.

---

### Task 1: Canonical VBPL resolver

**Files:** Create `src/vbpl_kb/vbpl_fallback.py`; create `tests/test_vbpl_fallback.py`.

**Interfaces:** `resolve_canonical_page(vbpl_id: str, html: str, checked_at: datetime) -> VerifiedFallback | QuarantineReason`.

- [ ] Write tests whose fixture HTML includes a Vietnamese title and explicit `Tình trạng hiệu lực: Còn hiệu lực`; assert `source_method == "canonical_page"`. Add a fixture missing the label and assert quarantine.
- [ ] Run `uv run pytest tests/test_vbpl_fallback.py -q`; expected failure because the resolver does not exist.
- [ ] Implement HTML text extraction and explicit label matching only for approved effect values; reject absent title/status.
- [ ] Run `uv run pytest tests/test_vbpl_fallback.py -q`; expected pass.
- [ ] Commit `feat: resolve canonical VBPL fallback`.

### Task 2: Persist quarantine and verified provenance

**Files:** Modify `src/vbpl_kb/state.py`, `src/vbpl_kb/models.py`, `src/vbpl_kb/crawl.py`; modify `tests/test_crawl.py`.

**Interfaces:** `StatusObservation` gains `source_url` and `source_method`; state exposes `record_quarantine(run_id, vbpl_id, reason)` and `quarantined_ids(run_id)`.

- [ ] Write a crawler test where primary status is absent and the fake fallback returns no verification; assert a quarantine event and stored reason.
- [ ] Run that test; expected failure because quarantine state is absent.
- [ ] Add the additive SQLite table and resolution flow. API-valid documents retain `source_method="api"`; canonical-valid documents use `"canonical_page"`.
- [ ] Run crawler tests; expected pass.
- [ ] Commit `feat: quarantine unverifiable VBPL records`.

### Task 3: Verified-only promotion

**Files:** Modify `src/vbpl_kb/publish.py`, `src/vbpl_kb/normalize.py`, `tests/test_publish.py`, `docs/operations.md`.

**Interfaces:** publisher reads verified snapshots only; metadata includes status provenance; previous active projections absent from the current verified set are deleted.

- [ ] Write a publisher test with one verified and one quarantined document; assert one upsert and deletion of the previously active quarantined projection.
- [ ] Run test; expected failure because publisher currently consumes every snapshot.
- [ ] Implement verified-set selection, deletion safety, and provenance metadata.
- [ ] Run `uv run pytest -q`, `uv run ruff check .`, and `uv run mypy src`; expected all pass.
- [ ] Commit `feat: promote only verified VBPL documents`.

## Self-review

The three tasks cover fallback parsing, audit/quarantine state, verified-only publication, stale-projection removal, metadata provenance, logs, and regression tests. No status is inferred from non-legal fields.
