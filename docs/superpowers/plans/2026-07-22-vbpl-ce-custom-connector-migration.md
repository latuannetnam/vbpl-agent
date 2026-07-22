# VBPL CE Custom Connector Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the production direct Onyx publisher with a pinned Onyx CE connector that indexes validated VBPL releases from a read-only shared Docker volume.

**Architecture:** Python retains sole responsibility for crawling, legal-status verification, normalization, cross-reference resolution, and release publication. It writes a checksummed candidate release and atomically promotes `active-release.json`. A derivative Onyx CE backend image registers `VBPLExportConnector`, which verifies the pointed manifest and yields bootstrap or incremental document batches. The pipeline triggers and observes Onyx’s connector API; it never posts per-document ingestion requests.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite, pytest, Typer, Docker Compose, PowerShell, Onyx CE Standard deployment, and OpenSearch.

## Global Constraints

- Official VBPL data/canonical pages are authoritative; Onyx is retrieval and Chat UI only.
- Release 1 is CE Chat plus a VBPL Legal Agent, not Search Mode.
- Production `run-daily` must not call `/onyx-api/ingestion`.
- Preserve SQLite, raw cache, and Docker volumes on failures; use retry/resume.
- Candidate validation completes before the atomic pointer change.
- Unknown or conflicting status stays historical-only and cannot support a current-law conclusion.
- Retain stable `vbpl:<official-id>` IDs, canonical URLs, article headings, `verified_at`, raw/normalized status, and reference edges.
- Do not auto-prune documents in Release 1.
- Commit overlays/patches; never hand-edit ignored `.onyx/onyx`.
- Keep the UI localhost-only and mount `/app/vbpl-export` read-only only into the Onyx background worker.

---

## File Structure

- Create: `src/vbpl_kb/releases.py` — release manifest schemas, SHA-256 validation, candidate writer, atomic pointer promotion.
- Create: `src/vbpl_kb/connector_control.py` — connector run/status API client.
- Create: `tests/test_releases.py`, `tests/test_connector_control.py`, `tests/test_release_deployment.py`.
- Create: `infra/onyx/onyx.lock.json`, `infra/onyx/Dockerfile.vbpl`, `infra/onyx/docker-compose.vbpl-connector.yml`, `infra/onyx/patches/vbpl-export-connector.patch`, `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py`, and `scripts/bootstrap-onyx.ps1`.
- Modify: `models.py`, `state.py`, `normalize.py`, `publish.py`, `config.py`, `cli.py`, `docker-compose.vbpl.yml`, `scripts/start-onyx.ps1`, `.env.example`, operator docs, and their existing focused tests.

### Task 1: Create connector-ready legal projections

**Files:**
- Modify: `src/vbpl_kb/models.py`, `src/vbpl_kb/normalize.py`, `src/vbpl_kb/publish.py`
- Test: `tests/test_normalize.py`, `tests/test_publish.py`

**Interfaces:**
- Produces `normalize_legal_status(raw_status: str | None) -> str`.
- Produces `build_projection(raw, status, revision, references) -> OnyxDocument` with no HTTP calls.

- [ ] **Step 1: Write failing status-provenance tests**

```python
def test_normalize_instrument_emits_verified_status_and_article_headings() -> None:
    doc = normalize_instrument(
        {"id": "123", "title": "Nghị định số 12/2024/NĐ-CP", "fullText": "Điều 1. Nội dung"},
        StatusObservation(vbpl_id="123", eff_status="Còn hiệu lực", eff_from=None,
            checked_at=datetime(2026, 7, 22, tzinfo=UTC), content_hash="raw-sha",
            run_id="vbpl-2026-07-22", status_source="api"),
        "vbpl-2026-07-22",
    )
    assert doc.document_id == "vbpl:123"
    assert "## Điều 1." in doc.content
    assert doc.metadata["legal_status_normalized"] == "in_force"
    assert doc.metadata["verified_at"] == "2026-07-22T00:00:00+00:00"
```

- [ ] **Step 2: Run it and confirm failure**

Run: `uv run pytest tests/test_normalize.py::test_normalize_instrument_emits_verified_status_and_article_headings -q`

Expected: FAIL because the extra status field and metadata do not exist.

- [ ] **Step 3: Implement projection status fields**

```python
def normalize_legal_status(raw_status: str | None) -> str:
    value = (raw_status or "").casefold()
    if "hết hiệu lực một phần" in value:
        return "partially_repealed"
    if "còn hiệu lực" in value:
        return "in_force"
    if "hết hiệu lực" in value or "bãi bỏ" in value:
        return "repealed"
    if "ngưng hiệu lực" in value or "tạm ngừng" in value:
        return "suspended"
    if "chưa có hiệu lực" in value:
        return "not_yet_effective"
    return "unknown"
```

Add `status_source: str = "api"` to `StatusObservation`. Add `legal_status_raw`, `legal_status_normalized`, `status_source`, `verified_at`, and deterministic reference metadata. Refactor `Publisher` to use the pure builder while retaining the legacy client until Task 3.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_normalize.py tests/test_publish.py -q`
Expected: PASS.

```powershell
git add src/vbpl_kb/models.py src/vbpl_kb/normalize.py src/vbpl_kb/publish.py tests/test_normalize.py tests/test_publish.py
git commit -m "feat: add connector-ready legal projections"
```

### Task 2: Publish immutable source releases

**Files:**
- Create: `src/vbpl_kb/releases.py`, `tests/test_releases.py`
- Modify: `src/vbpl_kb/models.py`, `src/vbpl_kb/state.py`, `tests/test_state.py`

**Interfaces:**
- `ReleaseExporter(store, export_dir).write_candidate(run_id) -> ReleaseManifest`
- `ReleaseExporter.promote(manifest) -> ActiveRelease`
- `active-release.json` fields: `release_id`, `manifest_path`, `manifest_sha256`, `published_at`.

- [ ] **Step 1: Write failing atomic-pointer tests**

```python
def test_invalid_candidate_does_not_replace_existing_pointer(tmp_path: Path, store: StateStore) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    active = exporter.promote(exporter.write_candidate("good"))
    with pytest.raises(ReleaseBlocked, match="checksum"):
        exporter.promote(ReleaseManifest("bad", Path("missing"), "bad", 1))
    assert exporter.read_active() == active
```

- [ ] **Step 2: Run it and confirm failure**

Run: `uv run pytest tests/test_releases.py -q`
Expected: FAIL with `ModuleNotFoundError: vbpl_kb.releases`.

- [ ] **Step 3: Implement candidate and pointer validation**

```python
def _write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
```

Write sorted document JSON under `releases/<run_id>/documents`, then the manifest after all SHA-256 checks succeed. Re-read the manifest in `promote`, reject paths outside the selected release, verify every checksum, then atomically replace the pointer. Add a `release_runs` table for `candidate`, `active`, and `blocked` states. Reject any run whose status is not `completed` or coverage is not `1.0`.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_releases.py tests/test_state.py -q`
Expected: PASS.

```powershell
git add src/vbpl_kb/releases.py src/vbpl_kb/models.py src/vbpl_kb/state.py tests/test_releases.py tests/test_state.py
git commit -m "feat: publish immutable VBPL export releases"
```

### Task 3: Use Onyx connector control from the CLI

**Files:**
- Create: `src/vbpl_kb/connector_control.py`, `tests/test_connector_control.py`
- Modify: `src/vbpl_kb/config.py`, `src/vbpl_kb/cli.py`, `tests/test_cli.py`, `tests/test_config.py`

**Interfaces:**
- `OnyxConnectorClient.trigger(connector_id: int, from_beginning: bool = False) -> int`
- `OnyxConnectorClient.wait_for_indexed(connector_id: int, timeout_seconds: float) -> None`
- New settings: `export_dir`, `onyx_connector_id`, `onyx_connector_run_once_path`, `onyx_connector_status_path`, `onyx_connector_timeout_seconds`.

- [ ] **Step 1: Write failing API and CLI tests**

```python
@respx.mock
def test_trigger_posts_run_once() -> None:
    route = respx.post("http://onyx:8080/admin/connector/run-once").mock(
        return_value=httpx.Response(200, json={"success": True, "data": 1}))
    client = OnyxConnectorClient(Settings(onyx_base_url="http://onyx:8080", onyx_connector_id=7))
    assert client.trigger(7) == 1
    assert route.calls.last.request.json() == {
        "connector_id": 7, "credential_ids": None, "from_beginning": False
    }
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `uv run pytest tests/test_connector_control.py tests/test_cli.py -q`
Expected: FAIL because connector control is absent.

- [ ] **Step 3: Implement the documented Onyx API contract**

```python
def trigger(self, connector_id: int, from_beginning: bool = False) -> int:
    response = self._request("POST", "/admin/connector/run-once", json={
        "connector_id": connector_id, "credential_ids": None, "from_beginning": from_beginning,
    })
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is not True or not isinstance(payload.get("data"), int):
        raise ConnectorControlError("Onyx did not accept the connector trigger")
    return payload["data"]
```

Add defaults for `VBPL_KB_EXPORT_DIR=/app/data/exports`, connector run-once/status paths, and a 7200-second connector timeout. Make `run-daily` execute crawl → candidate/export/promote → trigger → wait, without constructing `OnyxIngestionClient`. Rename existing `publish` to `publish-legacy` if it is retained; its help must state that it is diagnostic-only.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_config.py tests/test_connector_control.py tests/test_cli.py -q`
Expected: PASS.

```powershell
git add src/vbpl_kb/connector_control.py src/vbpl_kb/config.py src/vbpl_kb/cli.py tests/test_connector_control.py tests/test_cli.py tests/test_config.py
git commit -m "feat: trigger VBPL Onyx connector from daily pipeline"
```

### Task 4: Implement the pinned Onyx CE connector overlay

**Files:**
- Create: `infra/onyx/onyx.lock.json`, `infra/onyx/patches/vbpl-export-connector.patch`
- Create: `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py`
- Create: `tests/test_release_deployment.py`

**Interfaces:**
- `VBPLExportConnector(LoadConnector, PollConnector)` reads `/app/vbpl-export/active-release.json`.
- `DocumentSource.VBPL_EXPORT` maps to this connector in Onyx’s static registry.

- [ ] **Step 1: Write failing overlay tests**

```python
def test_connector_patch_registers_ce_source_without_pruning() -> None:
    patch = Path("infra/onyx/patches/vbpl-export-connector.patch").read_text(encoding="utf-8")
    assert 'VBPL_EXPORT = "vbpl_export"' in patch
    assert "VBPLExportConnector" in patch
    assert "SlimConnector" not in patch
```

- [ ] **Step 2: Run it and confirm failure**

Run: `uv run pytest tests/test_release_deployment.py -q`
Expected: FAIL because the lock and overlay are absent.

- [ ] **Step 3: Implement connector and patch**

```python
class VBPLExportConnector(LoadConnector, PollConnector):
    def __init__(self, export_root: str = "/app/vbpl-export", batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.export_root = Path(export_root)
        self.batch_size = batch_size

    def load_from_state(self) -> GenerateDocumentsOutput:
        yield from self._documents(changed_after=None)

    def poll_source(self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch) -> GenerateDocumentsOutput:
        yield from self._documents(changed_after=datetime.fromtimestamp(start, UTC))
```

`_documents` must validate pointer, manifest, document checksums, and relative paths before yielding any `Document`. It maps stable ID, title, semantic identifier, link, metadata, and content; polling filters the manifest `updated_at` field. Raise validation failure before output on an invalid release. Do not subclass `SlimConnector`.

Create the patch against the 40-character SHA in `onyx.lock.json`. It must add the enum, registry map, configuration validation, and the smallest admin form/type for a no-credential connector with a fixed `/app/vbpl-export` root.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_release_deployment.py -q`
Expected: PASS.

Run: `git -C .onyx/onyx apply --check ../../infra/onyx/patches/vbpl-export-connector.patch`
Expected: exit code 0 on the pinned revision.

```powershell
git add infra/onyx/onyx.lock.json infra/onyx/overlay infra/onyx/patches tests/test_release_deployment.py
git commit -m "feat: add Onyx CE VBPL export connector overlay"
```

### Task 5: Build and wire the derivative deployment

**Files:**
- Create: `infra/onyx/Dockerfile.vbpl`, `infra/onyx/docker-compose.vbpl-connector.yml`, `scripts/bootstrap-onyx.ps1`
- Modify: `scripts/start-onyx.ps1`, `docker-compose.vbpl.yml`, `.env.example`
- Modify: `tests/test_onyx_deployment.py`, `tests/test_deployment_files.py`, `tests/test_release_deployment.py`

**Interfaces:**
- Image `vbpl-onyx-backend:<revision>` serves `api_server` and `background`.
- The background service receives a read-only `VBPL_EXPORT_HOST_PATH:/app/vbpl-export:ro` mount.

- [ ] **Step 1: Write failing Compose safety tests**

```python
def test_connector_mount_is_read_only_and_background_only() -> None:
    compose = Path("infra/onyx/docker-compose.vbpl-connector.yml").read_text(encoding="utf-8")
    assert "background:" in compose
    assert "VBPL_EXPORT_HOST_PATH:/app/vbpl-export:ro" in compose
    assert "api_server:" in compose
```

- [ ] **Step 2: Run them and confirm failure**

Run: `uv run pytest tests/test_onyx_deployment.py tests/test_release_deployment.py -q`
Expected: FAIL because no derivative deployment exists.

- [ ] **Step 3: Implement reproducible bootstrap/start**

```powershell
git clone $lock.repository $onyxRoot
git -C $onyxRoot checkout --detach $lock.revision
git -C $onyxRoot apply --check $patchPath
git -C $onyxRoot apply $patchPath
docker compose --project-name vbpl-onyx build api_server background
```

`bootstrap-onyx.ps1` must refuse a non-empty checkout on the wrong revision, redact environment values, and never delete volumes. `start-onyx.ps1` calls it and includes the connector override while retaining scoped legacy shutdown. Remove required direct-ingestion route variables from production Compose and require export root/connector ID. Reserve NVIDIA GPU only for Onyx indexing/inference model servers.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_deployment_files.py tests/test_onyx_deployment.py tests/test_release_deployment.py -q`
Expected: PASS.

```powershell
git add infra/onyx scripts/bootstrap-onyx.ps1 scripts/start-onyx.ps1 docker-compose.vbpl.yml .env.example tests/test_deployment_files.py tests/test_onyx_deployment.py tests/test_release_deployment.py
git commit -m "feat: build pinned Onyx connector deployment"
```

### Task 6: Cut over docs, Agent, and real-data verification

**Files:**
- Modify: `README.md`, `docs/operations.md`, `docs/onyx-agent-setup.md`, `AGENTS.md`
- Modify: `benchmarks/v1.json`, `tests/test_evaluate.py`

**Interfaces:**
- Operator flow: bootstrap pinned Onyx → start → create connector once → set connector ID → run daily → inspect attempt.
- Agent scope: VBPL document set + Internal Search only, citations include legal status and `verified_at`.

- [ ] **Step 1: Write failing unknown-status safety test**

```python
def test_current_law_answer_requires_fresh_verified_status() -> None:
    report = evaluate_retrieval(
        [{"id": "unknown-status", "expected": {"requires_current_law_refusal": True}}],
        lambda _: [{"vbpl_id": "123", "status_fresh": False, "provision_key": "Điều 1"}],
    )
    assert report.passed is False
    assert report.current_law_safety_failures == 1
```

- [ ] **Step 2: Run it and confirm failure**

Run: `uv run pytest tests/test_evaluate.py -q`
Expected: FAIL until evaluation uses normalized status and `verified_at`.

- [ ] **Step 3: Implement final cutover and live checks**

Remove transition warnings and direct-ingestion setup from normal docs. Add benchmark cases for verified in-force article citation, partial repeal limitation, unknown refusal, and resolved/unresolved cross-reference. Configure the VBPL agent to refuse current-law claims without fresh verified retrieved status.

- [ ] **Step 4: Run full verification and real-data smoke test**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline run-daily --revision vbpl-connector-smoke
uv run vbpl-kb evaluate benchmarks/v1.json
```

Expected: automated commands exit 0. Record non-secret release ID, manifest checksum prefix, coverage, connector attempt status, indexed count, and the same grounded prompts for one cloud and one on-prem model. On failure, keep the old active export and diagnose without deleting stored state.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/operations.md docs/onyx-agent-setup.md AGENTS.md benchmarks/v1.json tests/test_evaluate.py
git commit -m "test: verify VBPL connector legal safety"
```

## Plan self-review

- Source release atomicity, per-document status evidence, citations, and references are covered by Tasks 1-2 and 6.
- Connector-only daily sync, full re-index recovery, and no automatic pruning are covered by Tasks 3-5.
- Pinned CE source overlay, read-only mount, localhost UI, and GPU boundaries are covered by Tasks 4-5.
- Agent-only CE interface plus cloud/on-prem grounded verification are covered by Task 6.
- Types flow consistently: `OnyxDocument` → manifest document JSON → Onyx `Document`; `ReleaseExporter` promotes source state; `OnyxConnectorClient` only triggers/observes indexing.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-vbpl-ce-custom-connector-migration.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batching work with checkpoints.

Which approach?
