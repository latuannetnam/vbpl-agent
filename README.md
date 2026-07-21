# VBPL Legal Knowledge Base Pipeline

A daily crawler and publication pipeline that snapshots the official Vietnamese legal databases (VBPL APIs), structures the legal documents (by Article, Clause, and Point), extracts and resolves cross-references, and ingests a validated legal corpus into **Onyx Standard**.

## Features

- **Daily Catalog Crawl**: Robust, retrying client snapshotting the official public VBPL gateway API with checkpoint resume support.
- **SQLite State Database**: Transaction ledger tracking raw JSON snapshots, checked dates, status observations, and projected metadata.
- **Reference Resolver**: Extracts cross-provisions (e.g. `Điều 8 Nghị định số 12/2024/NĐ-CP`), parses them to unique slugs, and resolves relationship edges (`repeals`, `amends`, `replaces`, etc.).
- **Onyx Ingestion**: Format-aware normalizer building clean markdown projections, formatting citations, appending related documents, and performing atomic index validation.
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
│   ├── onyx.py                    # Onyx Standard Ingestion API client
│   ├── publish.py                 # Ingestion gates and publisher controller
│   └── state.py                   # SQLite state engine
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
* `VBPL_KB_ONYX_API_KEY`: Authentication Bearer token.
* `VBPL_KB_DATA_DIR`: Directory for raw snapshots and database.

### Running CLI Commands

Use the registered script `vbpl-kb`:

```bash
# Get help and options list
uv run vbpl-kb --help

# Run daily crawl and publish to Onyx Standard
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
