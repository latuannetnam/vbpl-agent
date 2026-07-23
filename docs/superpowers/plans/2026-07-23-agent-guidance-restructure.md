# Agent Guidance Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make current repository guidance concise, navigable, and safe for Codex and Claude Code while separating it from historical designs and Onyx runtime administration.

**Architecture:** `AGENTS.md` and `README.md` become thin entrypoints that route readers to a set of current canonical documents. Three new documents own architecture, development workflow, and legal-data policy; existing runbooks retain only their operational or administrator responsibilities. A small offline pytest contract prevents the entrypoints and required authority blocks from drifting.

**Tech Stack:** Markdown, Python 3.12, pytest, Ruff, mypy, PowerShell, uv.

## Global Constraints

- Do not change `docs/vbpl-legal-agent-instruction.md`; it is a runtime prompt and is out of scope.
- Official VBPL evidence remains authoritative; Onyx is an internal retrieval and chat interface.
- Preserve the fail-closed legal-data rules, raw-evidence retention, and checkpointed recovery requirements.
- Do not delete `data/state.sqlite3`, `data/raw`, Docker volumes, or historical plans/specifications.
- `AGENTS.md` and `README.md` must not link to `docs/superpowers/specs/` or `docs/superpowers/plans/`.
- Every current document must contain `Status`, `Applies to`, `Use for`, and `Do not use for` fields.
- Documentation tests must run offline and inspect only stable document contracts, not arbitrary prose.
- Preserve unrelated working-tree changes and run the full verification suite before the final commit.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `AGENTS.md` | Concise coding-agent entrypoint, safety directives, task routing, and verification gate. |
| `README.md` | Human onboarding, current quick start, and current-document map. |
| `docs/architecture.md` | Current system boundaries, ownership, code map, and connector integration contract. |
| `docs/development-workflow.md` | Current change workflow, task classification, test discipline, and documentation update rule. |
| `docs/legal-data-policy.md` | Complete legal-data safety policy and change-impact rules. |
| `docs/operations.md` | Operational execution, Docker lifecycle, observability, and recovery instructions. |
| `docs/onyx-agent-setup.md` | Onyx administrator configuration, explicitly separate from coding-agent guidance. |
| `tests/test_documentation.py` | Offline contract checks for document authority metadata and entrypoint links. |

## Task 1: Establish Canonical Development Documents and Their Contract

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/development-workflow.md`
- Create: `docs/legal-data-policy.md`
- Create: `tests/test_documentation.py`

**Interfaces:**
- Consumes: the current production behavior documented in `AGENTS.md`, `docs/operations.md`, the existing Onyx overlay, and the approved design at `docs/superpowers/specs/2026-07-23-agent-guidance-restructure-design.md`.
- Produces: three current canonical documents with a uniform authority block; `test_current_development_documents_have_authority_blocks()` validates their required fields.

- [ ] **Step 1: Write the failing documentation-contract test**

Create `tests/test_documentation.py` with this exact initial content:

```python
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
CURRENT_DEVELOPMENT_DOCS = (
    "docs/architecture.md",
    "docs/development-workflow.md",
    "docs/legal-data-policy.md",
)
AUTHORITY_FIELDS = (
    "**Status:** Current",
    "**Applies to:**",
    "**Use for:**",
    "**Do not use for:**",
)


@pytest.mark.parametrize("relative_path", CURRENT_DEVELOPMENT_DOCS)
def test_current_development_documents_have_authority_blocks(
    relative_path: str,
) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    for field in AUTHORITY_FIELDS:
        assert field in text, f"{relative_path} is missing {field}"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: FAIL with `FileNotFoundError` for `docs/architecture.md`.

- [ ] **Step 3: Create `docs/architecture.md`**

Create the document with this content structure and wording:

```markdown
# VBPL Knowledge Base Architecture

**Status:** Current
**Applies to:** Pipeline, release, connector, Onyx-overlay, and infrastructure changes.
**Use for:** Understanding component boundaries, code ownership, data flow, and implementation constraints.
**Do not use for:** Docker recovery commands or configuring the running Onyx Legal Agent.

## System boundary

The official VBPL public gateway API and canonical VBPL pages are the legal source. The pipeline acquires and validates that evidence; the release exporter publishes complete immutable releases; the custom Onyx connector indexes an already-promoted release; Onyx provides retrieval and chat. Onyx and the Hugging Face dataset never establish legal force.

## Data flow and ownership

Official VBPL API and canonical pages -> raw snapshots and SQLite state -> normalization and legal-status verification -> reference resolution -> checksummed candidate release -> atomic active-release pointer -> read-only export mount -> VBPL Export Connector -> Onyx index -> scoped VBPL Legal Agent.

The crawler owns acquisition and resume. The normalizer and state layer own recorded evidence. The release layer owns validation and active-pointer promotion. The connector only converts a complete active release into Onyx documents. Onyx owns chunking, embedding, indexing, retrieval, and the chat user interface.

## Implementation map

| Area | Primary files |
| --- | --- |
| Settings and CLI | `src/vbpl_kb/config.py`, `src/vbpl_kb/cli.py` |
| Official API and canonical-page fallback | `src/vbpl_kb/vbpl_client.py`, `src/vbpl_kb/vbpl_fallback.py` |
| Crawl and persisted source state | `src/vbpl_kb/crawl.py`, `src/vbpl_kb/state.py` |
| Schema, normalization, and references | `src/vbpl_kb/models.py`, `src/vbpl_kb/normalize.py`, `src/vbpl_kb/references.py` |
| Document projection and releases | `src/vbpl_kb/publish.py`, `src/vbpl_kb/releases.py` |
| Legacy diagnostic publisher and connector trigger | `src/vbpl_kb/onyx.py`, `src/vbpl_kb/connector_control.py` |
| Onyx custom connector and frontend overlay | `infra/onyx/overlay/` |
| Local Onyx lifecycle | `scripts/bootstrap-onyx.ps1`, `scripts/start-onyx.ps1`, `infra/onyx/docker-compose.vbpl-*.yml` |

## Release and connector contract

The pipeline writes a candidate release beneath an immutable revision directory, validates coverage and checksums, then atomically updates `active-release.json`. The connector reads only the pointed-to active release through `/app/vbpl-export`; it never reads candidate or temporary paths. A connector failure preserves the existing index and is retried without deleting or recreating the connector.

`VBPLExportConnector` implementations must yield `list[Document]` batches from `poll_source()` and `load_from_state()` using `self.batch_size`. Export connectors yield every document in the complete promoted manifest and do not discard records with `changed_after`. The backend, background worker, and web frontend overlay must be updated together when a custom source changes; `scripts/bootstrap-onyx.ps1` builds `api_server`, `background`, and `web_server`.

## Dependency rules

The standard daily path is `run-daily` followed by the persistent VBPL Export Connector. `publish-legacy` is diagnostic-only; do not add a production dependency on direct Onyx ingestion APIs. The exported corpus is mounted read-only in the connector services. The host UI port is configurable with `ONYX_WEB_UI_PORT`; pipeline containers reach Onyx internally through the project-owned Docker network, not a host UI URL.

## Background

Historical plans and specifications preserve the rationale for prior decisions. This document is the current implementation instruction; consult a historical record only when this document identifies an unresolved decision that it does not describe.
```

- [ ] **Step 4: Create `docs/development-workflow.md`**

Create the document with this content:

```markdown
# VBPL Knowledge Base Development Workflow

**Status:** Current
**Applies to:** All repository code, test, infrastructure, and documentation changes.
**Use for:** Classifying a task, choosing current guidance, implementing safely, and reporting verification.
**Do not use for:** Daily operations or editing the running Onyx Legal Agent configuration.

## Start every task

Inspect the working tree first and preserve unrelated changes. Classify the task before editing:

| Change | Read first | Likely locations |
| --- | --- | --- |
| Crawl, schemas, normalization, status, or references | `docs/legal-data-policy.md`, `docs/architecture.md` | `src/vbpl_kb/`, `tests/` |
| Exports, release promotion, or connector input | `docs/legal-data-policy.md`, `docs/architecture.md` | `publish.py`, `releases.py`, `state.py` |
| Connector, overlay, Compose, or bootstrap | `docs/architecture.md`, `docs/operations.md` | `infra/onyx/`, `scripts/`, Compose files |
| Daily execution, Docker, incident, or recovery | `docs/operations.md` | `scripts/`, Compose files |
| Onyx Legal Agent UI configuration | `docs/onyx-agent-setup.md` | Runtime administration only |

## Change loop

1. Read the applicable current documents and focused existing tests.
2. Add or update a focused regression test before changing production behavior.
3. Make the smallest coherent change that satisfies the test and preserves the legal-data policy.
4. Update the canonical document that owns any changed behavior or operation; use links rather than duplicate prose.
5. Run focused tests, then the required full verification set.
6. Report changed files, commands run, outcomes, and any deliberately unverified external boundary.

## Verification gate

Run these commands before committing:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Use Docker Compose as the default path for daily pipeline execution. Rebuild the pipeline image before `docker compose run`, because `run` does not rebuild it. Keep secrets out of commands, logs, tests, documentation, and commits.

## Current versus historical guidance

Use `AGENTS.md` and the current documents linked from it as implementation instructions. Treat `docs/superpowers/specs/` and `docs/superpowers/plans/` as historical records. Read one only when a current document explicitly directs you to background for an unresolved design decision.
```

- [ ] **Step 5: Create `docs/legal-data-policy.md`**

Create the document with this content:

```markdown
# VBPL Legal-Data Policy

**Status:** Current
**Applies to:** Source acquisition, state, normalization, references, releases, connector metadata, retrieval, and evaluation changes.
**Use for:** Preserving provenance, legal-status, promotion, freshness, and recovery safety requirements.
**Do not use for:** Runtime Onyx user administration or general Docker lifecycle commands.

## Authority and provenance

The official VBPL service (`vbpl.vn` and its public gateway API) is the legal authority. Every indexed instrument retains its official source URL, legal status, verification time, corpus revision, provision structure, and retained raw evidence. The Hugging Face dataset is bootstrap or coverage-comparison input only; it never establishes current legal status.

## Legal-status evidence

Never infer legal force from editorial fields such as `status: Publish` or `reviewStatus`. Use `effStatus` or explicitly verified official canonical-page evidence. A record with missing, stale, failed, expired, suspended, conflicting, or unparseable status evidence is not support for a current-law conclusion. It may be indexed as `unknown` only after raw evidence is retained.

## Releases and relationships

Do not promote a partial, schema-invalid, or checksum-invalid source release. Preserve the previous active export when candidate validation is blocked. Treat unresolved legal-effect relationships as unresolved; only explicit official evidence creates amendment, replacement, or repeal edges. A document reference alone never establishes legal effect.

## Recovery and retention

Do not delete `data/state.sqlite3`, `data/raw`, or the project Docker volume merely to recover a crawl. The crawler is checkpointed and resumes the same revision, retrying missing detail snapshots. A full recrawl and data deletion require explicit user approval.

## Change impact

Changes to `vbpl_client.py`, `vbpl_fallback.py`, `crawl.py`, `normalize.py`, `models.py`, `references.py`, `state.py`, `publish.py`, `releases.py`, or connector metadata must add focused coverage for the affected evidence path. The test must demonstrate that invalid or incomplete official evidence cannot silently become a current-law claim or a promoted release.
```

- [ ] **Step 6: Run the focused test to verify it passes**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: PASS with three passing parameterized cases.

- [ ] **Step 7: Commit the canonical-document foundation**

```powershell
git add docs/architecture.md docs/development-workflow.md docs/legal-data-policy.md tests/test_documentation.py
git commit -m "docs: add canonical development guidance"
```

## Task 2: Rewrite Coding-Agent and Onboarding Entrypoints

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: the three canonical documents produced by Task 1.
- Produces: thin agent and onboarding entrypoints; `test_entrypoints_link_only_to_current_documents()` verifies required current links and rejects dated spec/plan links.

- [ ] **Step 1: Extend the failing contract test for entrypoints**

Append this exact code to `tests/test_documentation.py`:

```python

ENTRYPOINTS = ("AGENTS.md", "README.md")
CURRENT_DOCUMENT_LINKS = (
    "docs/architecture.md",
    "docs/development-workflow.md",
    "docs/legal-data-policy.md",
    "docs/operations.md",
    "docs/onyx-agent-setup.md",
)


@pytest.mark.parametrize("relative_path", ENTRYPOINTS)
def test_entrypoints_have_authority_blocks(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    for field in AUTHORITY_FIELDS:
        assert field in text, f"{relative_path} is missing {field}"


@pytest.mark.parametrize("relative_path", ENTRYPOINTS)
def test_entrypoints_link_only_to_current_documents(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    for document in CURRENT_DOCUMENT_LINKS:
        assert document in text, f"{relative_path} is missing {document}"
    assert "docs/superpowers/specs/" not in text
    assert "docs/superpowers/plans/" not in text
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: FAIL because the current entrypoints lack authority blocks, current-document links, and still reference `docs/superpowers/specs/`.

- [ ] **Step 3: Replace `AGENTS.md` with the concise coding-agent entrypoint**

Replace the file with the following content:

```markdown
# VBPL Legal Knowledge Base: Coding-Agent Guide

**Status:** Current
**Applies to:** Codex, Claude Code, and maintainers changing this repository.
**Use for:** First-read guardrails, task routing, and required verification before repository changes.
**Do not use for:** Onyx Legal Agent runtime configuration, daily operator recovery steps, or historical design decisions.

## Project boundary

This repository builds an internal Vietnamese legal knowledge base. Official VBPL API and canonical-page evidence are authoritative. The pipeline acquires and validates that evidence; Onyx is the internal indexing, retrieval, and chat interface. The Hugging Face dataset is bootstrap or coverage-comparison input only.

## Read the current document for the task

| Task | Read first | Main locations |
| --- | --- | --- |
| Crawl, schema, normalization, legal status, or references | [Legal-data policy](docs/legal-data-policy.md), [architecture](docs/architecture.md) | `src/vbpl_kb/`, `tests/` |
| Export, release promotion, or connector input | [Legal-data policy](docs/legal-data-policy.md), [architecture](docs/architecture.md) | `publish.py`, `releases.py`, `state.py` |
| Onyx connector, overlay, Compose, or bootstrap | [Architecture](docs/architecture.md), [operations](docs/operations.md) | `infra/onyx/`, `scripts/`, Compose files |
| Daily execution, Docker, incident, or recovery | [Operations](docs/operations.md) | `scripts/`, Compose files |
| Onyx Legal Agent UI configuration | [Onyx agent setup](docs/onyx-agent-setup.md) | Runtime administration only |

Read [the development workflow](docs/development-workflow.md) for every change. Read the focused existing tests before modifying crawler, normalization, reference, state, release, connector, or publication behavior.

## Non-negotiable rules

- Preserve official source URL, legal status, verification time, corpus revision, provision structure, and raw evidence for every indexed instrument.
- Use `effStatus` or verified official canonical-page evidence for legal status; never infer legal force from editorial fields.
- Never promote partial, schema-invalid, or checksum-invalid releases. Keep the prior active export when a candidate is blocked.
- Keep unresolved legal-effect relationships unresolved unless explicit official evidence establishes them.
- Never use stale, failed, absent, expired, suspended, or conflicting evidence for a current-law claim.
- Do not delete `data/state.sqlite3`, `data/raw`, or a Docker volume merely to recover a crawl. A full recrawl needs explicit user approval.
- Do not commit `.env`, API keys, raw snapshots, database files, generated Onyx configuration, or untracked edits under `.onyx/onyx`.
- Do not add a production dependency on the diagnostic direct-ingestion path; the daily path uses the validated export and persistent connector.

## Safe development loop

1. Inspect the working tree and preserve unrelated changes.
2. Read the applicable current document and focused tests.
3. Add or update a focused regression test before production behavior changes.
4. Make the smallest coherent change and update the canonical document that owns changed behavior or operations.
5. Run focused tests, then the full verification set.

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Historical records in `docs/superpowers/` explain prior decisions but are not current implementation instructions. Use them only when a current document explicitly names them as background.
```

- [ ] **Step 4: Replace `README.md` with concise onboarding and a documentation map**

Replace the file with the following content:

```markdown
# VBPL Legal Knowledge Base Pipeline

**Status:** Current
**Applies to:** Developers and operators starting or maintaining the local VBPL knowledge-base stack.
**Use for:** Project orientation, prerequisites, current quick-start commands, and documentation discovery.
**Do not use for:** Detailed architecture contracts, legal-data policy interpretation, incident recovery, or Onyx Legal Agent configuration.

This project snapshots official Vietnamese legal databases, validates and structures the records, publishes immutable verified releases, and makes them searchable through an internal Onyx Community Edition deployment. Official VBPL evidence remains authoritative; Onyx provides indexing, retrieval, and chat.

## Prerequisites

- Windows PowerShell, Docker Desktop, and `uv`.
- An untracked `.env` created from `.env.example`.
- A local Onyx API key and connector ID only when connector-trigger features require them. Never commit or print those values.

## Quick start

Install the locked Python environment:

```powershell
uv sync
```

Start or update the project-owned Onyx stack:

```powershell
.\scripts\start-onyx.ps1
```

Run the daily pipeline, inspect the active revision, and run verification:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run vbpl-kb run-daily --db-path data/state.sqlite3
uv run vbpl-kb status --db-path data/state.sqlite3
uv run pytest -q
uv run ruff check .
uv run mypy src
```

For the Docker-first daily execution and recovery procedure, use the [operations runbook](docs/operations.md).

## Documentation map

- [Coding-agent guide](AGENTS.md) — task routing, safety rules, and verification gate.
- [Architecture](docs/architecture.md) — boundaries, ownership, code map, and connector contract.
- [Development workflow](docs/development-workflow.md) — safe change and verification process.
- [Legal-data policy](docs/legal-data-policy.md) — provenance, status, promotion, and recovery rules.
- [Operations](docs/operations.md) — Docker lifecycle, daily execution, observability, and recovery.
- [Onyx agent setup](docs/onyx-agent-setup.md) — administrator configuration of the running legal-research agent.

Date-stamped material under `docs/superpowers/` is historical decision and planning context. It is not the operational source of truth; use the current documents above for work on this repository.
```

- [ ] **Step 5: Run the focused test to verify it passes**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: PASS with seven passing cases: three canonical-document checks, two entrypoint authority-block checks, and two entrypoint-link checks.

- [ ] **Step 6: Commit the entrypoint rewrite**

```powershell
git add AGENTS.md README.md tests/test_documentation.py
git commit -m "docs: streamline agent and project entrypoints"
```

## Task 3: Separate Operations and Runtime Administration from Development Guidance

**Files:**
- Modify: `docs/operations.md`
- Modify: `docs/onyx-agent-setup.md`
- Modify: `tests/test_documentation.py`

**Interfaces:**
- Consumes: the current-document links created in Tasks 1 and 2.
- Produces: scope-labeled runbooks with no dated design-spec links; the documentation contract validates authority fields for all current documents.

- [ ] **Step 1: Extend the failing authority-block test to include existing runbooks**

Replace the `CURRENT_DEVELOPMENT_DOCS` tuple in `tests/test_documentation.py` with:

```python
CURRENT_DEVELOPMENT_DOCS = (
    "docs/architecture.md",
    "docs/development-workflow.md",
    "docs/legal-data-policy.md",
    "docs/operations.md",
    "docs/onyx-agent-setup.md",
)
```

Append this exact test:

```python

@pytest.mark.parametrize(
    "relative_path",
    ("docs/operations.md", "docs/onyx-agent-setup.md"),
)
def test_runbooks_do_not_link_to_dated_design_specs(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "docs/superpowers/specs/" not in text
    assert "superpowers/specs/" not in text
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: FAIL because both current runbooks lack the authority block and `docs/operations.md` links to a dated design specification.

- [ ] **Step 3: Refocus `docs/operations.md`**

Make these exact changes:

1. Replace the title and dated-spec introduction with:

   ```markdown
   # VBPL Knowledge Base Operations Runbook

   **Status:** Current
   **Applies to:** Local Docker lifecycle, scheduled daily pipeline runs, observability, and recovery.
   **Use for:** Starting Onyx, running the pipeline, reading outcomes, and recovering safely from failed runs.
   **Do not use for:** Choosing code architecture, changing legal-data policy, or configuring the running Onyx Legal Agent.

   For component boundaries and connector contracts, read the [architecture](architecture.md). For provenance, status, promotion, and data-retention rules, read the [legal-data policy](legal-data-policy.md).
   ```

2. Replace the existing `## System Architecture` section with `## Operational boundary` containing only this paragraph:

   ```markdown
   The pipeline uses persisted SQLite state, retained raw snapshots, immutable export releases, and a project-owned Onyx stack. The daily job must leave the prior active release and indexed corpus available when source validation or connector indexing fails. Architecture details belong in the [architecture](architecture.md); this runbook contains the commands and recovery actions.
   ```

3. Keep `Running CLI Commands`, `Docker Compose Deployment`, `Project-owned local Onyx`, and `Chat and Legal Agent release surface`, but remove the numbered `Production Connector Workflow` section. Replace it with:

   ```markdown
   ## Daily outcome and safe failure handling

   `run-daily` resumes the persisted crawl, validates a candidate release, promotes only a complete checksummed export, and requests connector indexing. A blocked candidate leaves the active-release pointer unchanged. A connector failure preserves the previously indexed corpus; record the failure, correct the cause, and retry without deleting state, raw snapshots, volumes, or the connector.
   ```

4. In the Docker section, place the required rebuild command directly before the existing `docker compose ... run` command:

   ```powershell
   docker compose -f docker-compose.vbpl.yml build vbpl-pipeline
   docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
   ```

5. Keep the relative link to `onyx-agent-setup.md`; it is a current runtime-administration guide.

- [ ] **Step 4: Label `docs/onyx-agent-setup.md` as runtime administration**

Insert this exact authority block immediately after the H1 heading:

```markdown
**Status:** Current
**Applies to:** Onyx administrators configuring the running `VBPL Legal Research` agent and its document-set scope.
**Use for:** Admin-UI setup, runtime feature restrictions, and grounded-answer configuration.
**Do not use for:** Repository code changes, connector implementation, or Docker recovery.
```

Do not otherwise change its legal-agent instructions in this task.

- [ ] **Step 5: Run the focused test to verify it passes**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: PASS with eleven passing cases: five current-document authority checks, two entrypoint authority checks, two entrypoint-link checks, and two runbook dated-spec-link checks.

- [ ] **Step 6: Commit the runbook separation**

```powershell
git add docs/operations.md docs/onyx-agent-setup.md tests/test_documentation.py
git commit -m "docs: separate operations from development guidance"
```

## Task 4: Verify the Complete Documentation Contract

**Files:**
- Modify: `AGENTS.md` only if a failed verification identifies a missing required command or current-document link.
- Modify: `README.md` only if a failed verification identifies a broken quick-start or documentation-map link.
- Modify: `docs/architecture.md`, `docs/development-workflow.md`, `docs/legal-data-policy.md`, `docs/operations.md`, or `docs/onyx-agent-setup.md` only if a failed verification identifies a missing authority field or broken current-document link.
- Modify: `tests/test_documentation.py` only if a check is nondeterministic or contradicts the approved documentation contract.

**Interfaces:**
- Consumes: all documentation and tests created by Tasks 1–3.
- Produces: a verified current-document layer with no dated plans/specifications in coding-agent or onboarding entrypoints.

- [ ] **Step 1: Run the documentation contract in isolation**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_documentation.py -q
```

Expected: PASS with eleven passing cases.

- [ ] **Step 2: Inspect the staged documentation diff for unintended duplication and whitespace errors**

Run:

```powershell
git diff --check
git diff -- AGENTS.md README.md docs/architecture.md docs/development-workflow.md docs/legal-data-policy.md docs/operations.md docs/onyx-agent-setup.md tests/test_documentation.py
```

Expected: no `git diff --check` output; the diff shows only the planned canonical-document migration and documentation test.

- [ ] **Step 3: Run the complete repository verification gate**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected: all tests pass, Ruff reports no violations, and mypy reports no errors.

- [ ] **Step 4: Commit final verification adjustments only when needed**

If Steps 1–3 required no changes, do not create an empty commit. If they required a correction, commit exactly the corrected documentation and test files:

```powershell
git add AGENTS.md README.md docs/architecture.md docs/development-workflow.md docs/legal-data-policy.md docs/operations.md docs/onyx-agent-setup.md tests/test_documentation.py
git commit -m "test: verify documentation guidance contract"
```

## Plan Self-Review

- **Spec coverage:** Task 1 creates the three canonical documents and places architecture, workflow, and legal-data policy in separate owners. Task 2 makes `AGENTS.md` and `README.md` concise current entrypoints and removes their dated-spec references. Task 3 removes the operations runbook's dated-spec reference, reduces duplicated architecture prose, and separates runtime administration. Tasks 1–3 add the required authority blocks and deterministic link contract; Task 4 runs the complete verification gate.
- **Placeholder scan:** The plan contains no `TBD`, `TODO`, deferred implementation marker, or unspecified test behavior. Every change step names exact paths, content, or commands.
- **Type consistency:** `tests/test_documentation.py` uses `ROOT`, `CURRENT_DEVELOPMENT_DOCS`, `AUTHORITY_FIELDS`, `ENTRYPOINTS`, and `CURRENT_DOCUMENT_LINKS` consistently. The expected focused-test count is three in Task 1, seven in Task 2, and eleven in Task 3 and Task 4: five authority cases, two entrypoint authority cases, two entrypoint link cases, and two runbook dated-spec-link cases.
