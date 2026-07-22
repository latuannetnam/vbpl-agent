# VBPL Legal Knowledge Base Pipeline

A daily crawler and publication pipeline that snapshots the official Vietnamese
legal databases (VBPL APIs), structures the legal documents by Article, Clause,
and Point, extracts and resolves cross-references, and makes a validated legal
corpus available to **Onyx Community Edition (CE)**.

Release 1 uses stock Onyx Chat UI and a scoped VBPL Legal Agent. It does not use
the gated standalone Onyx Search Mode UI. The approved target architecture is a
project-owned Onyx `VBPL Export Connector` that reads validated releases from a
read-only shared Docker volume. See
[`docs/superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md`](docs/superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md).

> **Migration status:** the current code still contains a direct Onyx ingestion
> publisher. It is retained only while the connector migration is implemented;
> new production behavior must follow the approved connector design rather than
> extend the direct API path.

## Features

- **Daily Catalog Crawl**: Robust, retrying client snapshotting the official public VBPL gateway API with persisted page-checkpoint resume. An incomplete catalog is non-promotable.
- **SQLite State Database**: Transaction ledger tracking raw JSON snapshots, checked dates, status observations, and projected metadata.
- **Reference Resolver**: Extracts cross-provisions (e.g. `Điều 8 Nghị định số 12/2024/NĐ-CP`), parses them to unique slugs, and resolves relationship edges (`repeals`, `amends`, `replaces`, etc.).
- **Immutable Legal Releases**: A complete candidate export is checksummed and
  promoted through an atomic active-release pointer only after validation.
- **Onyx CE Connector (target)**: A custom shared-volume connector performs
  bootstrap and incremental indexing without the direct per-document ingestion
  API.
- **Grounded Legal Agent**: Chat answers cite the official instrument,
  article/section, status, verification date, and canonical VBPL URL. A status
  that is missing, stale, or conflicting cannot support a current-law claim.
- **Quality Gates**: Multi-stage validation requiring 100% crawl coverage, valid metadata, and strict evidence before promoting active revision state.
- **Safety Benchmarks**: Evaluation tool testing search and citation retrieval against safety constraints (e.g. flagging stale or partial active corpus).

## File Structure

```text
├── benchmarks/
│   └── v1.json                    # Reviewed benchmark test cases
├── docker/
│   └── Dockerfile.pipeline        # Multi-stage production container
├── docs/
│   ├── onyx-agent-setup.md        # Onyx setup runbook and refuse rules
│   └── operations.md              # Operations runbook for CLI and Docker
├── src/vbpl_kb/
│   ├── cli.py                     # Command-line entry points
│   ├── client.py                  # VBPL official gateway API wrapper
│   ├── config.py                  # Validated settings using Pydantic Settings
│   ├── crawl.py                   # Checkpointed daily crawler
│   ├── evaluate.py                # Retrieval safety evaluation metrics
│   ├── models.py                  # Pydantic schemas and projection models
│   ├── normalize.py               # Markdown and provenance normalizer
│   ├── onyx.py                    # Legacy direct Onyx ingestion API client
│   ├── publish.py                 # Legacy publisher; replaced by export workflow
│   └── state.py                   # SQLite state engine
├── infra/onyx/                    # Planned pinned Onyx overlay and connector image
├── tests/                         # Full contract, unit, and mock test suite
├── docker-compose.vbpl.yml        # Docker Compose runner
└── pyproject.toml                 # Package and project configurations
```

## Quick Start

### Installation

Ensure you have [uv](https://github.com/astral-sh/uv) installed:

```bash
# Sync and install the locked package
uv sync
```

### Environment Configuration

Copy `.env.example` to `.env` and fill in the Onyx API Key:

```bash
cp .env.example .env
```

Available variables (prefixed with `VBPL_KB_`):
* `VBPL_KB_VBPL_GATEWAY_URL`: Gateway target URL.
* `VBPL_KB_ONYX_BASE_URL`: Onyx Standard endpoint.
* `VBPL_KB_ONYX_API_KEY`: Authentication Bearer token for the legacy direct
  publisher or administrative diagnostics; not a production dependency after
  the connector migration.
* `VBPL_KB_ONYX_INGESTION_UPSERT_PATH`, `VBPL_KB_ONYX_INGESTION_DELETE_PATH`, `VBPL_KB_ONYX_SEARCH_PATH`, `VBPL_KB_ONYX_HEALTH_PATH`: Verified routes for the pinned Onyx deployment; never infer these paths.
* `VBPL_KB_DATA_DIR`: Directory for raw snapshots and database.

### Running CLI Commands

Use the registered script `vbpl-kb`:

```bash
# Get help and options list
uv run vbpl-kb --help

# Current implementation: run daily crawl and direct publish. The approved
# connector workflow will replace this publication step.
uv run vbpl-kb run-daily

# Check the freshness status of the active revision
uv run vbpl-kb status

# Run search safety benchmarks
uv run vbpl-kb evaluate benchmarks/v1.json
```

### Running Tests

Run the full suite of unit, contract, and integration tests:

```bash
uv run pytest -v
```
