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

Before the first run, set `VBPL_KB_ONYX_API_KEY`. The checked-in local defaults use the verified Onyx paths: `/onyx-api/ingestion`, `/onyx-api/ingestion/{document_id}`, `/admin/search`, and `/health`.

No public ports are exposed. Data is persisted to the named volume `vbpl-pipeline-data`. A failed or incomplete catalog run remains non-promotable; the preceding active revision stays in place and becomes stale once it exceeds the configured freshness window.

## Project-owned local Onyx

Start the project-owned local Onyx Standard stack from the repository root. The
script clones the official Onyx source into ignored `.onyx/onyx`, stops the
known older Compose project named `onyx`, preserves its volumes, and starts the
replacement as `vbpl-onyx`.

```powershell
$env:ONYX_WEB_UI_PORT = '3001'
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
```

The UI is available only on localhost at `http://127.0.0.1:3001` by default.
Set `ONYX_WEB_UI_PORT` in the shell or the untracked repository `.env` to bind a
different localhost port. The API health endpoint is `http://127.0.0.1:8080/health`.

On first use, complete the basic-auth setup in the UI and create an Onyx API
key. Store it only in the untracked repository `.env`:

```dotenv
VBPL_KB_ONYX_API_KEY=replace-with-local-onyx-api-key
VBPL_KB_ONYX_BASE_URL=http://api_server:8080
```

The pipeline Compose service joins the `vbpl-onyx_default` network and resolves
`api_server` internally. Start Onyx before running the daily worker:

```powershell
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

To stop the project-owned stack without deleting data:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```
