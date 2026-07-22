# VBPL Knowledge Base Pipeline Operations Runbook

This document details the operation of the daily VBPL snapshot crawler and the
pinned Onyx CE custom export connector.

The authoritative design specification is
[`2026-07-22-vbpl-ce-custom-connector-design.md`](superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md).

## System Architecture

The pipeline consists of:
- A Python pipeline worker that queries the official VBPL APIs.
- SQLite state database (`data/state.sqlite3`) containing catalog metadata, snapshots, observations, and projection state.
- Local disk store (`data/raw/`) containing raw API snapshots.
- Immutable candidate/active export release releases in `data/exports/` with checksummed manifests.
- A pinned custom Onyx CE backend image (`vbpl-onyx-backend:latest`) containing the `VBPL Export Connector`.
- Onyx Standard deployment components, used by CE for connector workers and indexing.

## Running CLI Commands

Inside the virtual environment (via `uv run` or directly):

- **Status Check**: Check the health and freshness of the active revision.
  ```bash
  vbpl-kb status --db-path data/state.sqlite3
  ```
  Exits with code `2` if stale (older than `VBPL_KB_FRESHNESS_HOURS`) or partial.

- **Daily Pipeline**: Run discovery, fetching, normalization,
  reference resolution, candidate export, atomic pointer promotion, and trigger Onyx indexing.
  ```bash
  vbpl-kb run-daily --db-path data/state.sqlite3
  ```

- **Manual Crawl**: Run only the crawler.
  ```bash
  vbpl-kb crawl --db-path data/state.sqlite3 --revision vbpl-2026-07-22
  ```

- **Diagnostic Direct Ingestion (Legacy)**: Legacy direct ingestion for debugging only.
  ```bash
  vbpl-kb publish-legacy --db-path data/state.sqlite3 --revision vbpl-2026-07-22
  ```

## Docker Compose Deployment

The Compose file is a one-shot worker. Run it from a host scheduler once per day; it intentionally does not restart continuously:
```bash
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

The worker streams human-readable crawl and export counts to standard output.
For a detached invocation, follow its output with:

```powershell
docker compose -f docker-compose.vbpl.yml logs -f vbpl-pipeline
```

Set `VBPL_KB_ONYX_API_KEY` and `VBPL_KB_ONYX_CONNECTOR_ID` in `.env`.

No public pipeline ports are exposed. Data is persisted to the named volume
`vbpl-pipeline-data`. A failed or incomplete catalog run remains
non-promotable; the preceding active revision stays in place and becomes stale
once it exceeds the configured freshness window.

## Production Connector Workflow

The daily job performs:

1. Crawl and resume the official VBPL cache.
2. Normalize records, verify legal-status evidence, and resolve references.
3. Write a complete immutable candidate export with document and manifest
   checksums.
4. Validate the candidate, then atomically replace `active-release.json`.
5. Trigger the persistent `VBPL Export Connector` and wait for a successful
   indexing attempt.
6. Persist release coverage, verification counts, connector outcome, and
   failures in SQLite and stdout logs.

The connector reads the active export through a read-only Docker mount (`/app/vbpl-export`).
It performs full load for bootstrap/recovery and incremental polling for daily
changes. Automatic pruning is intentionally disabled in Release 1: a document
missing from one catalog crawl must not silently disappear from legal history.

A release with an `unknown` legal status is searchable only as historical
material. The Legal Agent must not describe it as currently effective. Candidate
validation failure must not move the active pointer; connector failure preserves
the last indexed corpus and is retried rather than repaired by automatic
connector recreation.

## Project-owned local Onyx

Start the project-owned local Onyx CE stack from the repository root:

```powershell
$env:ONYX_WEB_UI_PORT = '3001'
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
```

The startup script calls `scripts/bootstrap-onyx.ps1` to ensure the pinned Onyx revision is checked out, the custom connector patch is applied, overlay files are copied, and `vbpl-onyx-backend:latest` image is built.

The UI is available on localhost at `http://127.0.0.1:3001` by default.
The API health endpoint is `http://127.0.0.1:8080/health`.

Store API credentials in the untracked repository `.env`:

```dotenv
VBPL_KB_ONYX_API_KEY=replace-with-local-onyx-api-key
VBPL_KB_ONYX_CONNECTOR_ID=1
```

To stop the project-owned stack without deleting data:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```

## Chat and Legal Agent release surface

Release 1 exposes normal Onyx CE Chat and the scoped VBPL Legal Agent. Do not
configure or document a standalone Onyx Search Mode UI: it is not available in
the CE-only scope. The Legal Agent is limited to the VBPL connector/document
set and Internal Search; web search, code execution, and external write actions
remain disabled. See [Onyx agent setup](onyx-agent-setup.md) for the required
grounding and citation instructions.
