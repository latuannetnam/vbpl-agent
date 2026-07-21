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
  Exits with code `2` if stale (older than `VBPL_KB_FRESHNESS_HOURS`) or partial.

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

The Compose file is a one-shot worker. Run it from a host scheduler once per day; it intentionally does not restart continuously:
```bash
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

Before the first run, set `VBPL_KB_ONYX_BASE_URL`, `VBPL_KB_ONYX_API_KEY`, and the pinned Onyx routes (`VBPL_KB_ONYX_INGESTION_UPSERT_PATH`, optional `VBPL_KB_ONYX_INGESTION_DELETE_PATH`, `VBPL_KB_ONYX_SEARCH_PATH`, and optional `VBPL_KB_ONYX_HEALTH_PATH`). Do not guess those routes: verify them with an authenticated probe against the exact deployed Onyx version and retain a redacted response fixture.

No public ports are exposed. Data is persisted to the named volume `vbpl-pipeline-data`. A failed or incomplete catalog run remains non-promotable; the preceding active revision stays in place and becomes stale once it exceeds the configured freshness window.
