# VBPL Incremental Catalog Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Replace the daily full detail crawl and full Onyx re-index with a complete, metadata-only VBPL catalog scan that fetches and indexes only new or materially changed documents, while safely propagating confirmed deletions.

**Architecture:** Each run enumerates the complete official VBPL catalog and persists a canonical metadata fingerprint per document. Only new or changed fingerprints trigger a detail fetch and normalized-document update. Two consecutive successful complete catalog scans are required before a missing document becomes a tombstone. Release promotion still produces a self-contained, immutable full export for recovery, plus an immutable delta batch for Onyx. The connector full-loads from the active full manifest, polls delta manifests for upserts, and exposes all active IDs through Onyx slim-document enumeration so Onyx can prune confirmed tombstones.

**Tech Stack:** Python 3.12, SQLite, Pydantic, pytest, Ruff, mypy, official VBPL HTTP API, Onyx CE custom connector and Docker Compose overlay.

## Global Constraints

- Official VBPL API and canonical official-page evidence remain authoritative; preserve source URL, legal status, verification time, corpus revision, raw evidence, and provision structure.
- A failed or partial catalog scan must not classify deletions, alter the active release, or trigger an Onyx prune.
- Do not delete `data/state.sqlite3`, `data/raw`, Docker volumes, or use `scripts/reset-and-reindex-onyx.py` during normal sync. The reset script remains explicit recovery-only tooling.
- The production path remains validated export plus the persistent `vbpl_export` connector; do not introduce a production direct-ingestion path.
- An index-affecting schema, normalizer, or projection compatibility change requires an explicit full re-index/recovery workflow, not a silent delta update.
- Update current documentation, including `AGENTS.md` when its guidance changes, only after implementation and verification are complete. Do not make coding guidance depend on this dated plan.

---

### Task 1: Define catalog, change-set, and delta contracts

**Files:**
- Create: `src/vbpl_kb/catalog.py`
- Modify: `src/vbpl_kb/models.py`
- Modify: `src/vbpl_kb/__init__.py` if public exports are maintained there
- Create: `tests/test_catalog.py`

**Step 1: Write failing catalog-classification tests**

Add table-driven tests for:

- canonical fingerprint equality despite API key order;
- a newly observed ID classified as `new`;
- an existing ID whose title, number, type, official update time, legal status, or effective-to value changes classified as `changed`;
- an unchanged row classified as unchanged;
- IDs absent from a complete catalog represented as candidates, not immediate tombstones.

Use realistic VBPL metadata rows containing at least `id`, `title`, `docNum`, `docType`, `updatedDate`, `effStatus`, and `effTo`.

**Step 2: Run the focused test to confirm it fails**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_catalog.py -q
```

Expected: failure because the catalog contract and classifier do not exist.

**Step 3: Implement the smallest contract**

In `models.py`, add strongly typed models for a persisted catalog row and its comparison result, such as `CatalogEntry`, `CatalogChangeSet`, and `DeltaManifest`. In `catalog.py`, implement:

- parsing of raw gateway rows into the canonical row shape;
- deterministic UTF-8 JSON fingerprinting over only index-relevant source metadata;
- classification against the last successful catalog snapshot.

Keep a separate audit timestamp/evidence update path: an unchanged index fingerprint may record fresh official catalog observation locally, but must not by itself produce an Onyx upsert. Any material status/effective-value change must be included in the fingerprint and therefore fetch detail and update the index.

**Step 4: Re-run the focused tests**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_catalog.py -q
```

Expected: all catalog classification tests pass.

**Step 5: Commit**

```powershell
git add src/vbpl_kb/catalog.py src/vbpl_kb/models.py src/vbpl_kb/__init__.py tests/test_catalog.py
git commit -m "feat: define VBPL catalog change contracts"
```

### Task 2: Persist complete catalog snapshots, removals, and document versions

**Files:**
- Modify: `src/vbpl_kb/state.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_models.py` if model persistence is covered there

**Step 1: Write failing state tests**

Cover these sequences using a temporary state database:

1. A successful complete scan persists full rows and their fingerprints.
2. A partial/failed scan is recorded for diagnostics but cannot replace the latest successful baseline.
3. First complete-scan absence records a removal candidate only.
4. Second consecutive complete-scan absence creates a tombstone; a reappearance clears its candidate.
5. A changed document version and delta-batch manifest can be recorded and later queried in stable order.

**Step 2: Run the focused tests to confirm they fail**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_state.py -q
```

Expected: failure for the missing incremental state API.

**Step 3: Add migration-safe state tables and methods**

Extend `StateStore.initialize()` with append-safe tables for:

- catalog scan completeness and scan metadata;
- catalog observations/fingerprints by scan and document ID;
- removal candidates/tombstones with consecutive-complete-scan evidence;
- document versions and immutable delta-batch records.

Add narrow APIs with explicit inputs/outputs, for example `record_catalog_scan(...)`, `latest_catalog_entries()`, `finalize_catalog_scan(...)`, `record_document_version(...)`, `record_delta_batch(...)`, and `pending_delta_batches()`. Ensure only `complete=True` snapshots can become the baseline or advance absence counters.

**Step 4: Re-run the focused tests**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_state.py tests/test_models.py -q
```

Expected: complete/partial scan, two-scan tombstone, and delta persistence cases pass.

**Step 5: Commit**

```powershell
git add src/vbpl_kb/state.py tests/test_state.py tests/test_models.py
git commit -m "feat: persist incremental catalog sync state"
```

### Task 3: Change the crawler to fetch detail only for new or changed records

**Files:**
- Modify: `src/vbpl_kb/vbpl_client.py`
- Modify: `src/vbpl_kb/crawl.py`
- Modify: `tests/test_vbpl_client.py`
- Modify: `tests/test_crawl.py`

**Step 1: Write failing crawler tests**

Expand the fake client so catalog pages return metadata rows and track `get_detail()` calls. Test that:

- a first complete scan fetches each detail;
- a later complete scan fetches only new/changed IDs;
- unchanged rows retain current raw/normalized evidence and record audit observation only;
- pagination/HTTP/detail failure marks the run incomplete and produces neither tombstones nor release eligibility;
- the crawler output exposes changed IDs and confirmed tombstone IDs deterministically.

**Step 2: Run focused tests to confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_vbpl_client.py tests/test_crawl.py -q
```

Expected: existing crawler fetches every detail and lacks incremental summary data.

**Step 3: Implement the complete-catalog barrier**

Make `VBPLClient.list_catalog_page()` retain the full API metadata rather than only IDs. In `DailyCrawler.run()`:

1. page through the entire catalog and persist raw catalog observations;
2. only after all pages succeed, compare against the prior complete snapshot;
3. fetch details only for `new` and `changed` IDs, retaining existing retry/status/canonical fallback behavior;
4. finalize the catalog snapshot and absence counters only when both catalog enumeration and all required changed-detail work meet the existing coverage rules.

Return an explicit incremental run summary/change set so publication can distinguish upserts from confirmed deletes. Do not change the existing current-law validation gates.

**Step 4: Re-run focused tests**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_vbpl_client.py tests/test_crawl.py -q
```

Expected: tests prove the second run does not call detail for unchanged IDs and never tombstones from an incomplete scan.

**Step 5: Commit**

```powershell
git add src/vbpl_kb/vbpl_client.py src/vbpl_kb/crawl.py tests/test_vbpl_client.py tests/test_crawl.py
git commit -m "feat: crawl VBPL catalog incrementally"
```

### Task 4: Build immutable full releases and immutable delta batches

**Files:**
- Modify: `src/vbpl_kb/releases.py`
- Modify: `src/vbpl_kb/publish.py` if it owns export promotion helpers
- Modify: `tests/test_releases.py`
- Modify: `tests/test_release_deployment.py`

**Step 1: Write failing release tests**

Add coverage that:

- an incremental candidate contains every active document, with unchanged document JSON copied byte-for-byte from the previous valid active release;
- changed/new documents are rebuilt from the new validated evidence;
- confirmed tombstones are omitted from the next full manifest and appear in its delta batch;
- the delta manifest contains only upserts plus tombstone IDs, compatibility versions, checksum, and release identity;
- invalid/partial candidates leave the active pointer and prior export unchanged.

**Step 2: Run focused tests to confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_releases.py tests/test_release_deployment.py -q
```

Expected: current exporter builds an all-new release only from same-run snapshots and has no delta contract.

**Step 3: Refactor release construction**

Add an incremental release path, for example `write_incremental_candidate(run_id, change_set)`, that:

- requires a complete eligible crawl run;
- starts from the prior active full manifest, reuses unchanged files, writes validated upserts, and removes only confirmed tombstones;
- validates the resulting full manifest with existing checksum/schema gates;
- writes a separate immutable `delta-manifest.json` for the promoted release;
- persists its batch record only after promotion succeeds.

Retain the existing full `load_from_state` recovery contract. Add explicit compatibility fields for source schema, normalizer, and projection. Reject an incremental promotion if those versions require a full rebuild/re-index.

**Step 4: Re-run focused tests**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_releases.py tests/test_release_deployment.py -q
```

Expected: full recovery export remains self-contained, delta is minimal, and invalid candidates cannot promote.

**Step 5: Commit**

```powershell
git add src/vbpl_kb/releases.py src/vbpl_kb/publish.py tests/test_releases.py tests/test_release_deployment.py
git commit -m "feat: publish immutable VBPL delta batches"
```

### Task 5: Make the Onyx connector poll delta batches and enumerate active IDs for pruning

**Files:**
- Modify: `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py`
- Modify: `infra/onyx/patches/vbpl-export-connector.patch`
- Modify: `tests/test_vbpl_export_connector.py`
- Modify: `tests/test_release_deployment.py`

**Step 1: Write failing connector tests**

Test that:

- `load_from_state()` emits every document from the active full manifest;
- `poll_source(start, end)` emits only delta upserts selected by the persisted delta batch timestamps/identity;
- a no-change batch yields no documents;
- a slim-document enumeration returns all IDs in the active full manifest, rather than only delta IDs;
- malformed or incompatible manifests fail closed without emitting a partial stream.

Update the release-deployment assertion that currently forbids `SlimConnector`; it should instead require the patched connector to implement the appropriate Onyx pruning interface.

**Step 2: Run focused tests to confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_vbpl_export_connector.py tests/test_release_deployment.py -q
```

Expected: current `poll_source()` ignores its cursor and streams all active documents.

**Step 3: Implement the connector behavior**

Make `VBPLExportConnector` implement `SlimConnector` in addition to its current load/poll interfaces. Keep:

- `load_from_state()` reading the validated active full export;
- `poll_source()` reading only validated promoted delta manifests after the supplied start cursor;
- `retrieve_all_slim_docs()` enumerating all active full-manifest IDs so Onyx’s existing prune path deletes only IDs absent from the promoted active release.

Validate release/checksum/projection compatibility before emitting each stream. Modify the CE patch only as needed for imports/registration, and keep source type `vbpl_export` stable.

**Step 4: Re-run focused tests**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_vbpl_export_connector.py tests/test_release_deployment.py -q
```

Expected: delta polling is narrow and slim enumeration safely supports pruning of confirmed tombstones.

**Step 5: Commit**

```powershell
git add infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py infra/onyx/patches/vbpl-export-connector.patch tests/test_vbpl_export_connector.py tests/test_release_deployment.py
git commit -m "feat: poll VBPL export deltas in Onyx"
```

### Task 6: Orchestrate retries, document operations, and verify the live contract

**Files:**
- Modify: `src/vbpl_kb/cli.py`
- Modify: `src/vbpl_kb/connector_control.py` if trigger outcome/cursor reporting needs an API
- Modify: `tests/test_cli.py`
- Modify: `docs/architecture.md`
- Modify: `docs/operations.md`
- Modify: `docs/development-workflow.md`
- Modify: `AGENTS.md` only if its current routing or verification guidance changes
- Modify: `docs/onyx-agent-setup.md` only if source/verification behavior changes
- Modify: `tests/test_documentation.py`

**Step 1: Write failing orchestration and documentation tests**

Cover:

- an existing unacknowledged delta batch is retried before a newer delta batch;
- no Onyx trigger occurs when a complete crawl has no upserts and no tombstones;
- a blocked/partial candidate leaves the active release and connector untouched;
- the normal daily flow never invokes the reset/re-index script;
- documentation names incremental catalog scans, two-scan deletion confirmation, full-load recovery, delta polling, and full re-index compatibility boundaries.

**Step 2: Run focused tests to confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_cli.py tests/test_documentation.py -q
```

Expected: CLI always follows full crawler/export assumptions and current docs do not describe the operational delta lifecycle.

**Step 3: Implement bounded daily orchestration**

Update `run_daily` to:

1. retry any pending promoted delta delivery first;
2. run the complete metadata scan and changed-detail acquisition;
3. create and promote a validated incremental full release plus delta batch only when eligible;
4. trigger the persistent connector with `from_beginning=False` only when a promoted batch has work;
5. record delivery acknowledgment/error so retries are safe and idempotent.

Update current canonical documentation after the implementation is verified. Clearly distinguish normal delta operations from explicit full-reindex recovery, list the compatibility-change boundary, and retain the current source-grounded Onyx acceptance criteria. Do not add dated-plan links to `AGENTS.md`.

**Step 4: Run repository verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected: all repository checks pass.

**Step 5: Run operational acceptance in the existing local Onyx environment**

Follow the current operations document to bring up the configured local stack. Exercise one known upsert and one confirmed two-scan tombstone in a controlled test export, then verify:

- Onyx receives a narrow poll update rather than a full document stream;
- the active full export still supports `load_from_state` recovery;
- slim enumeration includes the complete active set and Onyx removes only the confirmed tombstone;
- `scripts/verify-schema-v2-index.py` validates the documented random sample;
- the configured Legal Agent’s `internal_search` tool returns `vbpl_export` evidence from the scoped document set.

Do not run `scripts/reset-and-reindex-onyx.py` for this acceptance. If a compatibility version changes, stop the delta path and use the separately authorized full-reindex recovery procedure.

**Step 6: Commit**

```powershell
git add src/vbpl_kb/cli.py src/vbpl_kb/connector_control.py tests/test_cli.py docs/architecture.md docs/operations.md docs/development-workflow.md AGENTS.md docs/onyx-agent-setup.md tests/test_documentation.py
git commit -m "feat: orchestrate incremental VBPL Onyx sync"
```

### Task 7: Review the implementation before integration

**Files:**
- Review the complete implementation diff and all changed tests/docs

**Step 1: Inspect the implementation diff and status**

```powershell
git status --short
git diff --check
git log --oneline -7
```

Expected: no whitespace errors, no unintended raw snapshots/database/configuration artifacts, and coherent task commits.

**Step 2: Request a focused code review**

Use `superpowers:requesting-code-review` before merging or opening a pull request. Provide the reviewer the approved design, this plan, the changed files, and verification evidence. Address any findings with focused tests before integration.

**Step 3: Complete integration**

Use `superpowers:finishing-a-development-branch` to choose the user-approved merge/PR/cleanup path after review and final verification.

