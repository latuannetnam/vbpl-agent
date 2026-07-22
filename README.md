# VBPL Legal Knowledge Base Pipeline

A daily crawler and publication pipeline that snapshots the official Vietnamese
legal databases (VBPL APIs), structures the legal documents by Article, Clause,
and Point, extracts and resolves cross-references, and makes a validated legal
corpus available to **Onyx Community Edition (CE)**.

Release 1 uses stock Onyx Chat UI and a scoped VBPL Legal Agent. It does not use
the gated standalone Onyx Search Mode UI. The architecture uses a project-owned
Onyx `VBPL Export Connector` that reads validated releases from a read-only
shared Docker volume. See
[`docs/superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md`](docs/superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md).

## Features

- **Daily Catalog Crawl**: Robust, retrying client snapshotting the official public VBPL gateway API with persisted page-checkpoint resume. An incomplete catalog is non-promotable.
- **SQLite State Database**: Transaction ledger tracking raw JSON snapshots, checked dates, status observations, and projected metadata.
- **Reference Resolver**: Extracts cross-provisions (e.g. `Điều 8 Nghị định số 12/2024/NĐ-CP`), parses them to unique slugs, and resolves relationship edges (`repeals`, `amends`, `replaces`, etc.).
- **Immutable Legal Releases**: A complete candidate export is checksummed and
  promoted through an atomic active-release pointer only after validation.
- **Onyx CE Connector**: A custom shared-volume connector performs bootstrap
  and incremental indexing without reliance on direct ingestion APIs.
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
│   ├── connector_control.py       # Onyx CE connector trigger client
│   ├── crawl.py                   # Checkpointed daily crawler
│   ├── evaluate.py                # Retrieval safety evaluation metrics
│   ├── models.py                  # Pydantic schemas and projection models
│   ├── normalize.py               # Markdown and provenance normalizer
│   ├── publish.py                 # Legal document projection builders
│   ├── releases.py                # Release exporter and pointer manager
│   └── state.py                   # SQLite state engine
├── infra/onyx/                    # Pinned Onyx overlay, connector patch, and Docker files
├── scripts/
│   ├── bootstrap-onyx.ps1         # Pinned Onyx setup and build script
│   └── start-onyx.ps1             # Local stack lifecycle script
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

Copy `.env.example` to `.env` and configure settings:

```bash
cp .env.example .env
```

Available variables (prefixed with `VBPL_KB_`):
* `VBPL_KB_VBPL_GATEWAY_URL`: Gateway target URL.
* `VBPL_KB_ONYX_BASE_URL`: Onyx Standard endpoint.
* `VBPL_KB_ONYX_API_KEY`: Authentication Bearer token for connector control.
* `VBPL_KB_ONYX_CONNECTOR_ID`: Pinned Onyx connector ID for `VBPL_EXPORT`.
* `VBPL_KB_EXPORT_DIR`: Shared export directory mounted into Onyx.
* `VBPL_KB_ONYX_SEARCH_PATH`, `VBPL_KB_ONYX_HEALTH_PATH`: Verified routes for the pinned Onyx deployment.
* `VBPL_KB_DATA_DIR`: Directory for raw snapshots and database.

### Running Local Onyx & Pipeline

Start Onyx stack:

```powershell
.\scripts\start-onyx.ps1
```

Run daily export and connector sync:

```bash
# Get help and options list
uv run vbpl-kb --help

# Daily crawl, export, and Onyx connector trigger
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
