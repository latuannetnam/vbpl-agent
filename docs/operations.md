# VBPL Knowledge Base Pipeline Operations Runbook

This document details the operation of the daily VBPL snapshot crawler and Onyx publisher pipeline.

## System Architecture

The pipeline consists of:
- A Python pipeline worker that queries the official VBPL APIs.
- SQLite state database (`data/state.sqlite3`) containing catalog metadata, snapshots, observations, and projection state.
- Local disk store (`data/raw/`) containing raw API snapshots.
- Pinned Onyx Standard instance where projections are indexed.

## Running CLI Commands

Inside the virtual environment (via `uv run` or directly):

- **Status Check**: Check the health and freshness of the active revision.
  ```bash
  vbpl-kb status --db-path data/state.sqlite3
  ```
  Exits with code `2` if stale (older than 24 hours) or partial.

- **Daily Pipeline**: Run discovery, fetching, normalization, reference resolution, and upsertion.
  ```bash
  vbpl-kb run-daily --db-path data/state.sqlite3
  ```

- **Manual Crawl**: Run only the crawler.
  ```bash
  vbpl-kb crawl --db-path data/state.sqlite3 --revision vbpl-2026-07-21
  ```

- **Manual Publish**: Publish an already completed crawl revision.
  ```bash
  vbpl-kb publish --db-path data/state.sqlite3 --revision vbpl-2026-07-21
  ```

## Docker Compose Deployment

Run the daily pipeline container with Docker Compose:
```bash
docker-compose -f docker-compose.vbpl.yml up -d
```

No public ports are exposed. Data is persisted to the named volume `vbpl-pipeline-data`.
