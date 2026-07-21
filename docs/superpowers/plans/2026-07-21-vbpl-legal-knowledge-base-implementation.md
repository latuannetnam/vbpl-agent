# VBPL Legal Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily official-VBPL crawl and verified Onyx corpus serving grounded Search UI and Chat Legal Agent results.

**Architecture:** A Python worker snapshots the official VBPL API, saves state in SQLite plus mounted files, resolves provisions and references, then upserts only a fully validated revision to Onyx Standard. Onyx remains independent from the crawler state store.

**Tech Stack:** Python 3.12, uv, httpx, Pydantic v2, SQLite, pytest, respx, Docker Compose, Onyx Standard.

## Global Constraints

- VBPL APIs are the legal authority; Hugging Face is bootstrap/comparison data only.
- Every `effStatus` and `effFrom` is refreshed daily. Failed/stale records cannot support a current-law answer.
- One Onyx document represents one instrument; its `Điều`/`Khoản`/`Điểm` headings are retained for citations.
- Legal-effect edges require explicit source evidence; ambiguous references are unresolved.
- Release 1 is internal Docker Compose, Basic Auth, a cloud and an on-premises model, and no Craft, Web Search, Code Execution, external MCP, SSO, or granular permissions.
- The workspace is not yet a Git repository. Initialize it in Task 1 and make each task’s commit.

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `.env.example` | Package/dependency and non-secret configuration contracts |
| `src/vbpl_kb/config.py` | Validated settings |
| `src/vbpl_kb/models.py`, `state.py` | Domain models, SQLite state, raw snapshot metadata |
| `src/vbpl_kb/vbpl_client.py`, `crawl.py` | Official API client and checkpointed daily crawl |
| `src/vbpl_kb/normalize.py`, `references.py` | Citation documents and legal reference graph |
| `src/vbpl_kb/onyx.py`, `publish.py`, `cli.py` | Ingestion adapter, publish gates, operational CLI |
| `tests/` | Contract/unit/end-to-end tests and VBPL fixtures |
| `docker/Dockerfile.pipeline`, `docker-compose.vbpl.yml` | Reproducible internal deployment |
| `docs/operations.md`, `docs/onyx-agent-setup.md` | Runbook and exact Onyx Agent configuration |
| `benchmarks/v1.json`, `src/vbpl_kb/evaluate.py` | Reviewed retrieval/citation acceptance benchmark |

---

### Task 1: Bootstrap a testable Python worker

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/vbpl_kb/__init__.py`
- Create: `src/vbpl_kb/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces `Settings` with `vbpl_gateway_url: str`, `onyx_base_url: str`, `onyx_api_key: SecretStr`, `data_dir: Path`, and `freshness_hours: int`.

- [ ] **Step 1: Initialize the repository and install dependencies**

```powershell
git init
git add docs/superpowers/specs/2026-07-21-vbpl-legal-knowledge-base-design.md
git commit -m "docs: add approved VBPL knowledge-base design"
uv init --python 3.12
uv add httpx pydantic pydantic-settings typer rich
uv add --dev pytest respx ruff mypy
```

- [ ] **Step 2: Write the failing settings test**

```python
from pathlib import Path
from vbpl_kb.config import Settings

def test_settings_uses_prefixed_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VBPL_KB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VBPL_KB_ONYX_API_KEY", "test-key")
    settings = Settings()
    assert settings.data_dir == tmp_path
    assert settings.onyx_api_key.get_secret_value() == "test-key"
    assert settings.freshness_hours == 24
```

- [ ] **Step 3: Verify failure**

Run: `uv run pytest tests/test_config.py -v`  
Expected: FAIL because `vbpl_kb.config` does not exist.

- [ ] **Step 4: Implement settings and sample environment**

```python
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VBPL_KB_", env_file=".env", extra="ignore")
    vbpl_gateway_url: str = "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public"
    onyx_base_url: str = "http://localhost:8080"
    onyx_api_key: SecretStr = SecretStr("")
    data_dir: Path = Path("data")
    freshness_hours: int = 24
    request_timeout_seconds: float = 30.0
    max_pages: int | None = None
```

Create `.env.example` for every field; leave the API key empty. Ignore `.env`, `data/`, `.venv/`, and cache directories.

- [ ] **Step 5: Verify and commit**

Run: `uv run pytest tests/test_config.py -v; uv run ruff check .`  
Expected: PASS; no lint findings.

```powershell
git add pyproject.toml uv.lock .gitignore .env.example src tests
git commit -m "feat: bootstrap VBPL pipeline settings"
```

### Task 2: Add immutable state and domain contracts

**Files:**
- Create: `src/vbpl_kb/models.py`, `src/vbpl_kb/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces `StatusObservation`, `LegalReference`, `CrawlRun`, and `OnyxDocument`.
- Produces `StateStore.open(path)`, `begin_run(revision)`, `record_snapshot(...)`, `record_status(observation)`, `latest_status(vbpl_id)`, and `finish_run(...)`.

- [ ] **Step 1: Write failing snapshot/status tests**

```python
from datetime import UTC, datetime
from vbpl_kb.models import StatusObservation
from vbpl_kb.state import StateStore

def test_snapshot_hash_and_latest_status(tmp_path) -> None:
    store = StateStore.open(tmp_path / "state.sqlite3")
    run_id = store.begin_run("vbpl-2026-07-21")
    assert store.record_snapshot(run_id, "123", "detail", '{"id":123}', "a") is True
    assert store.record_snapshot(run_id, "123", "detail", '{"id":123}', "a") is False
    status = StatusObservation("123", "Còn hiệu lực", "2024-01-01",
        datetime(2026, 7, 21, tzinfo=UTC), "a", run_id)
    store.record_status(status)
    assert store.latest_status("123") == status
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_state.py -v`  
Expected: FAIL because models/state do not exist.

- [ ] **Step 3: Implement models and SQLite schema**

Use Pydantic models and SQLite tables `crawl_runs`, `raw_snapshots`, `status_observations`, `legal_references`, and `onyx_projection`. Store raw response files at `data/raw/<revision>/<vbpl_id>-<endpoint>.json`; store their SHA-256 and relative path in SQLite. Add indexes on `(vbpl_id, checked_at DESC)` and `(from_vbpl_id, from_provision_key)`.

- [ ] **Step 4: Add failure-state coverage**

Add a test proving `finish_run(run_id, "partial", 0.99)` cannot replace the latest successful revision.  
Run: `uv run pytest tests/test_state.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/vbpl_kb/models.py src/vbpl_kb/state.py tests/test_state.py
git commit -m "feat: persist VBPL snapshots and status ledger"
```

### Task 3: Implement the observed VBPL API contract

**Files:**
- Create: `src/vbpl_kb/vbpl_client.py`
- Create: `tests/fixtures/vbpl/catalog-page.json`, `detail-current.json`, `detail-partial.json`
- Test: `tests/test_vbpl_client.py`

**Interfaces:**
- Produces `VBPLClient.list_catalog_page(page_number, page_size)` and `get_detail(vbpl_id)`.
- Raises `VBPLSchemaError` if required fields `data.id`, `data.title`, or `data.effStatus.name` are absent.

- [ ] **Step 1: Write failing client-contract tests**

```python
import httpx, pytest, respx
from vbpl_kb.vbpl_client import VBPLClient, VBPLSchemaError

@respx.mock
def test_detail_extracts_status(settings, load_fixture) -> None:
    respx.get(f"{settings.vbpl_gateway_url}/doc/123").mock(
        return_value=httpx.Response(200, json=load_fixture("detail-current.json")))
    assert VBPLClient(settings).get_detail("123").eff_status == "Còn hiệu lực"

@respx.mock
def test_detail_rejects_missing_status(settings) -> None:
    respx.get(f"{settings.vbpl_gateway_url}/doc/123").mock(
        return_value=httpx.Response(200, json={"data": {"id": 123, "title": "X"}}))
    with pytest.raises(VBPLSchemaError, match="effStatus.name"):
        VBPLClient(settings).get_detail("123")
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_vbpl_client.py -v`  
Expected: FAIL because `VBPLClient` does not exist.

- [ ] **Step 3: Implement client with bounded retries**

Implement `POST /doc/all` for catalog discovery and `GET /doc/{id}` for detail. Retry only `429,500,502,503,504` with exponential delays and preserve the complete JSON body. Use deterministic catalog sorting when the API supports it; do not treat view-count ordering as an incremental cursor.

- [ ] **Step 4: Verify schema and retry behavior**

Add a mock test returning 503 then 200 and assert two requests.  
Run: `uv run pytest tests/test_vbpl_client.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/vbpl_kb/vbpl_client.py tests
git commit -m "feat: add official VBPL gateway client"
```

### Task 4: Build the daily crawler and citation projection

**Files:**
- Create: `src/vbpl_kb/crawl.py`, `src/vbpl_kb/normalize.py`
- Test: `tests/test_crawl.py`, `tests/test_normalize.py`

**Interfaces:**
- Produces `DailyCrawler.run(revision) -> CrawlSummary`.
- Produces `normalize_instrument(raw, status, revision) -> OnyxDocument`.
- Each projected document has stable ID `vbpl:<vbpl_id>`, canonical VBPL link, metadata, and Markdown provision headings.

- [ ] **Step 1: Write failing crawl and Markdown tests**

```python
def test_crawl_continues_and_records_coverage(fake_client, store) -> None:
    fake_client.catalog_pages = [["1", "2", "3"]]
    fake_client.fail_detail_ids = {"2"}
    summary = DailyCrawler(fake_client, store).run("vbpl-2026-07-21")
    assert (summary.detail_count, summary.failed_ids, summary.coverage) == (2, ["2"], 2 / 3)

def test_projection_contains_citable_provenance(raw_instrument, status) -> None:
    document = normalize_instrument(raw_instrument, status, "vbpl-2026-07-21")
    assert document.document_id == "vbpl:123"
    assert "Status: Còn hiệu lực" in document.content
    assert "## Điều 8." in document.content
    assert document.metadata["status_checked_at"] == "2026-07-21T00:00:00+00:00"
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_crawl.py tests/test_normalize.py -v`  
Expected: FAIL because crawler/normalizer do not exist.

- [ ] **Step 3: Implement daily state refresh and normalization**

Persist a new status observation for every successfully fetched instrument even when content is unchanged. Checkpoint after every catalog page. A partial run is never promotable. Render provenance, then official text with recognized `Điều`, `Khoản`, `Điểm` headings. An unparsed body becomes `## Toàn văn` with `citation_structure=unparsed`, which blocks article-specific current-law conclusions.

- [ ] **Step 4: Add partial/unparsed tests and verify**

Test `Hết hiệu lực một phần` rendering and checkpoint restart.  
Run: `uv run pytest tests/test_crawl.py tests/test_normalize.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/vbpl_kb/crawl.py src/vbpl_kb/normalize.py tests
git commit -m "feat: crawl and normalize citation-ready legal records"
```

### Task 5: Add conservative legal-reference resolution

**Files:**
- Create: `src/vbpl_kb/references.py`
- Test: `tests/test_references.py`

**Interfaces:**
- Produces `extract_references(vbpl_id, provision_key, text)` and `resolve_reference(candidate, instrument_index)`.
- Permitted types: `cites`, `legal_basis`, `guides_implementation`, `amends`, `supplements`, `replaces`, `repeals`, `unknown`.

- [ ] **Step 1: Write failing explicit/ambiguous tests**

```python
def test_explicit_repeal_keeps_evidence(instrument_index) -> None:
    edge = resolve_reference(
        extract_references("A", "dieu-1", "Bãi bỏ Điều 8 Nghị định số 12/2024/NĐ-CP.")[0],
        instrument_index)
    assert (edge.relation_type, edge.to_vbpl_id) == ("repeals", "B")
    assert "Bãi bỏ" in edge.source_quote

def test_ambiguous_reference_is_not_guessed(instrument_index) -> None:
    edge = resolve_reference(extract_references("A", "dieu-1", "Theo Nghị định số 12.")[0], instrument_index)
    assert edge.to_vbpl_id is None
    assert edge.relation_type == "unknown"
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_references.py -v`  
Expected: FAIL because reference functions do not exist.

- [ ] **Step 3: Implement resolver and related-documents section**

Normalize document type/number/year, use explicit Vietnamese legal-effect verbs, and match by unique document number plus optional issuer/date. Preserve source quote and offsets. If no unique target exists, create an unresolved `unknown` edge. Append `## Văn bản liên quan` with resolved target status, canonical link, source provision, and type.

- [ ] **Step 4: Verify neutral citations and status labels**

Add tests for a resolved neutral `cites` edge and a partially effective target label.  
Run: `uv run pytest tests/test_references.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/vbpl_kb/references.py tests/test_references.py
git commit -m "feat: resolve VBPL legal cross references"
```

### Task 6: Implement verified Onyx ingestion and publish gates

**Files:**
- Create: `src/vbpl_kb/onyx.py`, `src/vbpl_kb/publish.py`
- Test: `tests/test_onyx.py`, `tests/test_publish.py`

**Interfaces:**
- Produces `OnyxIngestionClient.healthcheck()`, `upsert(document)`, and `delete(document_id)`.
- Produces `Publisher.publish(run_id) -> PublishSummary` and raises `PublishBlocked`.

- [ ] **Step 1: Write failing upsert/gate tests**

```python
@respx.mock
def test_upsert_sends_stable_id_and_provenance(settings, onyx_document) -> None:
    route = respx.post(f"{settings.onyx_base_url}/api/ingestion/document").mock(
        return_value=httpx.Response(200, json={"id": "vbpl:123"}))
    OnyxIngestionClient(settings).upsert(onyx_document)
    assert b"vbpl:123" in route.calls[0].request.content
    assert b"status_checked_at" in route.calls[0].request.content

def test_partial_run_is_blocked(store, fake_onyx) -> None:
    run_id = store.begin_run("vbpl-2026-07-21")
    store.finish_run(run_id, "partial", 0.99)
    with pytest.raises(PublishBlocked, match="crawl run is not complete"):
        Publisher(store, fake_onyx).publish(run_id)
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_onyx.py tests/test_publish.py -v`  
Expected: FAIL because clients/publisher do not exist.

- [ ] **Step 3: Confirm and implement the exact Onyx ingestion contract**

Before writing production request code, make an authenticated contract probe against the pinned Onyx version and commit a redacted response fixture. Replace the provisional path in the test with that verified API path/body. Implement bearer authentication, typed non-2xx errors without secrets, stable IDs, changed-document upserts, deleted-document removal, and projection persistence.

Block promotion unless coverage is exactly `1.0`, every catalog ID has a status observation, required citation metadata exists, no duplicate identity exists, and each legal-effect edge has explicit evidence. Mark the revision active only after every Onyx operation succeeds.

- [ ] **Step 4: Verify idempotence, deletion, and stale behavior**

Add tests for repeated upsert, 401/500 error handling, stale active revision, and deleted instrument removal.  
Run: `uv run pytest tests/test_onyx.py tests/test_publish.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/vbpl_kb/onyx.py src/vbpl_kb/publish.py tests
git commit -m "feat: publish validated VBPL revisions to Onyx"
```

### Task 7: Expose operational CLI and internal Docker deployment

**Files:**
- Create: `src/vbpl_kb/cli.py`, `docker/Dockerfile.pipeline`, `docker-compose.vbpl.yml`
- Create: `docs/operations.md`, `docs/onyx-agent-setup.md`
- Test: `tests/test_cli.py`, `tests/test_deployment_files.py`

**Interfaces:**
- Produces commands `vbpl-kb crawl`, `publish`, `run-daily`, and `status`.
- `status` exits 2 for stale/partial active corpus and outputs JSON.

- [ ] **Step 1: Write failing CLI/deployment tests**

```python
def test_status_exits_two_when_revision_is_stale(runner, stale_store) -> None:
    result = runner.invoke(app, ["status", "--data-dir", str(stale_store.data_dir)])
    assert result.exit_code == 2
    assert '"status":"stale"' in result.stdout.replace(" ", "")

def test_compose_uses_persistent_internal_volume() -> None:
    text = Path("docker-compose.vbpl.yml").read_text()
    assert "vbpl-pipeline-data:/app/data" in text
    assert "restart: unless-stopped" in text
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_cli.py tests/test_deployment_files.py -v`  
Expected: FAIL because files do not exist.

- [ ] **Step 3: Implement CLI, container, and runbooks**

Make `run-daily` execute crawl, normalization/reference resolution, validation, and publication; it exits 1 on blocked publish and preserves the prior active revision. The Dockerfile installs the locked package, runs as non-root, and uses `/app/data`. The Compose overlay exposes no public ports and mounts the named data volume.

Document Basic Auth, Onyx Standard, one `vbpl-verified` source, Search UI, a Legal Agent scoped only to that source, Cloud default/local alternative, and this required agent refusal: `Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.` State explicitly: Web Search disabled, Code Execution disabled, Craft disabled, external MCP disabled.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_cli.py tests/test_deployment_files.py -v; docker build -f docker/Dockerfile.pipeline -t vbpl-kb-pipeline:test .`  
Expected: PASS and completed image build.

- [ ] **Step 5: Commit**

```powershell
git add src docker docker-compose.vbpl.yml docs tests
git commit -m "feat: package internal VBPL Onyx operation"
```

### Task 8: Add reviewed benchmark and release acceptance checks

**Files:**
- Create: `benchmarks/v1.json`, `src/vbpl_kb/evaluate.py`
- Modify: `src/vbpl_kb/cli.py`, `docs/operations.md`
- Test: `tests/test_evaluate.py`

**Interfaces:**
- Produces `evaluate_retrieval(cases, search) -> EvaluationReport`.
- Adds `vbpl-kb evaluate benchmarks/v1.json`; it fails on any stale current-law result or incorrect cited provision.

- [ ] **Step 1: Write failing safety test**

```python
def test_evaluation_rejects_stale_current_law_result() -> None:
    report = evaluate_retrieval(
        [{"query": "Q", "expected_vbpl_id": "1", "expected_provision_key": "dieu-1",
          "requires_current_status": True}],
        lambda _: [{"vbpl_id": "1", "provision_key": "dieu-1", "status_fresh": False}])
    assert report.current_law_safety_failures == 1
    assert report.passed is False
```

- [ ] **Step 2: Verify failure**

Run: `uv run pytest tests/test_evaluate.py -v`  
Expected: FAIL because `evaluate_retrieval` does not exist.

- [ ] **Step 3: Implement evaluation and add real reviewed cases**

Calculate top-10 provision recall, citation correctness, VBPL-link presence, current-law safety, and legal-effect-edge correctness. Add only human-reviewed real VBPL IDs/links to the benchmark: exact number lookup, natural-language provision, current, partial, expired, not-yet-effective, amendment/repeal, and ambiguous-reference cases.

- [ ] **Step 4: Run complete verification**

```powershell
uv run pytest -v
uv run ruff check .
uv run mypy src
uv run vbpl-kb --help
```

Expected: all checks pass and help lists `crawl`, `publish`, `run-daily`, `status`, and `evaluate`.

- [ ] **Step 5: Record the pilot gate and commit**

Add the operations checklist: crawl a reviewed subset; publish to non-production Onyx; validate an exact Search UI result/link; validate every Chat citation; force stale state and verify refusal; then rerun the same case on the on-premises model.

```powershell
git add benchmarks src tests docs/operations.md
git commit -m "test: add VBPL legal retrieval acceptance benchmark"
```

## Plan Self-Review

- **Spec coverage:** Tasks 2–4 implement daily authority, snapshots, status, provision citations; Task 5 implements legal relationships; Task 6 implements Onyx publishing and stale gates; Task 7 implements Search/Chat deployment and simple controls; Task 8 implements benchmark, model-path, and pilot acceptance. Release-2 MCP remains intentionally out of this Release-1 plan.
- **Placeholder scan:** The only contract intentionally deferred to a live probe is the exact Onyx ingestion endpoint, because it must match the pinned deployed Onyx version. Task 6 makes the probe and committed redacted fixture an explicit blocking step and prohibits a guessed production endpoint.
- **Type consistency:** `Settings`, `StateStore`, `VBPLClient`, `DailyCrawler`, `OnyxDocument`, `OnyxIngestionClient`, `Publisher`, and `EvaluationReport` are defined before later tasks consume them. Document IDs are consistently `vbpl:<vbpl_id>`.
