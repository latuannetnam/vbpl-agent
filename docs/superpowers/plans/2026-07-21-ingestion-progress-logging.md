# Ingestion Progress Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit clear, human-readable ingestion progress in Docker logs while retaining the existing crawl and publication behavior.

**Architecture:** `DailyCrawler` and `Publisher` receive an optional `ProgressReporter` callback that emits stable phase/count lines. The Typer commands pass `typer.echo`, so one event becomes one Docker-log line. The callback is optional, leaving library callers behaviorally unchanged.

**Tech Stack:** Python 3.12, Typer, pytest.

## Global Constraints

- Log phase names, cumulative counts, catalog pages, and failures only.
- Never log secrets, request headers, or document body text.
- Do not change SQLite schema, crawl coverage semantics, normalization, references, or Onyx request payloads.
- Emit events at phase boundaries and after every 100 processed documents.

---

### Task 1: Add crawler progress reporting

**Files:**
- Modify: `src/vbpl_kb/crawl.py`
- Modify: `tests/test_crawl.py`

**Interfaces:**
- Produces: `DailyCrawler(client, store, progress: Callable[[str], None] | None = None)`.
- Emits: `crawl: catalog page {page} discovered; documents={count}`, `crawl: fetched {done}/{total} documents (failed={failed})`, and `crawl: completed; documents={done}/{total} (failed={failed})`.

- [ ] **Step 1: Write failing crawler event test**

```python
def test_crawl_reports_catalog_and_fetch_progress(fake_client, store) -> None:
    events: list[str] = []
    DailyCrawler(fake_client, store, progress=events.append).run("run-1")
    assert events[0] == "crawl: catalog page 1 discovered; documents=2"
    assert events[-1] == "crawl: completed; documents=2/2 (failed=0)"
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_crawl.py::test_crawl_reports_catalog_and_fetch_progress -q`

Expected: FAIL because `DailyCrawler` has no `progress` parameter.

- [ ] **Step 3: Implement optional callback and batch emission**

```python
ProgressReporter = Callable[[str], None]

def _report(self, message: str) -> None:
    if self.progress is not None:
        self.progress(message)
```

Call `_report` after each discovered catalog page, at every 100 completed or failed detail attempts, and once after `finish_run`.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_crawl.py -q`

Expected: all crawler tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/vbpl_kb/crawl.py tests/test_crawl.py
git commit -m "feat: report crawler progress"
```

### Task 2: Add publisher progress reporting

**Files:**
- Modify: `src/vbpl_kb/publish.py`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Produces: `Publisher(store, onyx, progress: Callable[[str], None] | None = None)`.
- Emits: `publish: preparing {total} documents`, `publish: upserted {done}/{total} documents`, `publish: deleted {done}/{total} stale documents`, and a completion line.

- [ ] **Step 1: Write failing publisher event test**

```python
def test_successful_publish_reports_progress(store, fake_onyx) -> None:
    events: list[str] = []
    summary = Publisher(store, fake_onyx, progress=events.append).publish("run-1")
    assert events[0] == "publish: preparing 1 documents"
    assert events[-1] == f"publish: completed; upserted={summary.upserted_count} deleted={summary.deleted_count}"
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_publish.py::test_successful_publish_reports_progress -q`

Expected: FAIL because `Publisher` has no `progress` parameter.

- [ ] **Step 3: Implement optional callback and batch emission**

Add the same `_report` pattern. Report before processing snapshots, every 100 upserts, every 100 stale deletions, and after `set_active_run`.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/test_publish.py -q`

Expected: all publisher tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/vbpl_kb/publish.py tests/test_publish.py
git commit -m "feat: report publication progress"
```

### Task 3: Render events in CLI and document Docker log access

**Files:**
- Modify: `src/vbpl_kb/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: optional progress callbacks from Tasks 1 and 2.
- Produces: `crawl`, `publish`, and `run-daily` commands that stream component events to standard output.

- [ ] **Step 1: Write failing CLI output test**

```python
def test_run_daily_streams_component_progress(monkeypatch, tmp_path) -> None:
    result = runner.invoke(app, ["run-daily", "--db-path", str(tmp_path / "state.sqlite3")])
    assert "crawl: catalog page" in result.output
    assert "publish: completed;" in result.output
```

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/test_cli.py::test_run_daily_streams_component_progress -q`

Expected: FAIL because the CLI does not pass a reporter into its components.

- [ ] **Step 3: Pass `typer.echo` as the progress reporter**

```python
crawler = DailyCrawler(client, store, progress=typer.echo)
publisher = Publisher(store, onyx, progress=typer.echo)
```

Add this operations command:

```powershell
docker compose -f docker-compose.vbpl.yml logs -f vbpl-pipeline
```

- [ ] **Step 4: Verify the complete feature**

Run:

```powershell
uv run pytest tests/test_crawl.py tests/test_publish.py tests/test_cli.py -q
uv run ruff check .
uv run mypy src
```

Expected: all tests, lint, and type checks pass.

- [ ] **Step 5: Commit**

```bash
git add src/vbpl_kb/cli.py tests/test_cli.py docs/operations.md
git commit -m "feat: stream ingestion progress to Docker logs"
```

## Self-review

Tasks 1-2 provide optional component-level reporting with periodic counts; Task 3 exposes it in the CLI and documents the Docker command. The plan has no schema or Onyx-payload changes, logs no sensitive values, and uses the same callback type consistently.
