# VBPL Knowledge Base Pipeline Operations Runbook

This document details the operation of the daily VBPL snapshot crawler and its
transition to an Onyx CE shared-volume connector.

The authoritative target is
[`2026-07-22-vbpl-ce-custom-connector-design.md`](superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md).
Until that connector is implemented, the existing `publish` and `run-daily`
commands still use the legacy direct-ingestion client. Do not mistake those
current commands for the approved production architecture.

## System Architecture

The pipeline consists of:
- A Python pipeline worker that queries the official VBPL APIs.
- SQLite state database (`data/state.sqlite3`) containing catalog metadata, snapshots, observations, and projection state.
- Local disk store (`data/raw/`) containing raw API snapshots.
- An immutable candidate/active export release model with checksummed manifests
  (target implementation).
- A pinned custom Onyx CE backend image containing the VBPL Export Connector
  (target implementation).
- Onyx Standard deployment components, used by CE for connector workers and
  indexing.

## Running CLI Commands

Inside the virtual environment (via `uv run` or directly):

- **Status Check**: Check the health and freshness of the active revision.
  ```bash
  vbpl-kb status --db-path data/state.sqlite3
  ```
  Exits with code `2` if stale (older than `VBPL_KB_FRESHNESS_HOURS`) or partial.

- **Daily Pipeline (current)**: Run discovery, fetching, normalization,
  reference resolution, and legacy direct upsertion.
  ```bash
  vbpl-kb run-daily --db-path data/state.sqlite3
  ```

- **Manual Crawl**: Run only the crawler.
  ```bash
  vbpl-kb crawl --db-path data/state.sqlite3 --revision vbpl-2026-07-21
  ```

- **Manual Publish (legacy)**: Directly publish an already completed crawl
  revision. It is a debugging/transition tool and will be replaced by immutable
  export generation plus connector triggering.
  ```bash
  vbpl-kb publish --db-path data/state.sqlite3 --revision vbpl-2026-07-21
  ```

## Docker Compose Deployment

The Compose file is a one-shot worker. Run it from a host scheduler once per day; it intentionally does not restart continuously:
```bash
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

The worker streams human-readable crawl and publish counts to standard output.
For a detached invocation, follow its output with:

```powershell
docker compose -f docker-compose.vbpl.yml logs -f vbpl-pipeline
```

Before the first legacy direct-publisher run, set `VBPL_KB_ONYX_API_KEY`. The
checked-in local defaults use the verified Onyx paths: `/onyx-api/ingestion`,
`/onyx-api/ingestion/{document_id}`, `/admin/search`, and `/health`. These
routes are not the future production ingestion interface.

No public pipeline ports are exposed. Data is persisted to the named volume
`vbpl-pipeline-data`. A failed or incomplete catalog run remains
non-promotable; the preceding active revision stays in place and becomes stale
once it exceeds the configured freshness window.

## Target connector workflow

After the connector migration, the daily job will:

1. Crawl and resume the official VBPL cache.
2. Normalize records, verify legal-status evidence, and resolve references.
3. Write a complete immutable candidate export with document and manifest
   checksums.
4. Validate the candidate, then atomically replace `active-release.json`.
5. Trigger the persistent `VBPL Export Connector` and wait for a successful
   indexing attempt.
6. Persist release coverage, verification counts, connector outcome, and
   failures in SQLite and stdout logs.

The connector reads the active export through a read-only Docker mount. It
performs full load for bootstrap/recovery and incremental polling for daily
changes. Automatic pruning is intentionally disabled in Release 1: a document
missing from one catalog crawl must not silently disappear from legal history.

A release with an `unknown` legal status is searchable only as historical
material. The Legal Agent must not describe it as currently effective. Candidate
validation failure must not move the active pointer; connector failure preserves
the last indexed corpus and is retried rather than repaired by automatic
connector recreation.

## Project-owned local Onyx

Start the current project-owned local Onyx Standard stack from the repository
root. The script clones the official Onyx source into ignored `.onyx/onyx`,
stops the known older Compose project named `onyx`, preserves its volumes, and
starts the replacement as `vbpl-onyx`.

The connector migration changes this to a reproducible derivative build: the
repository will pin the upstream revision, apply a committed VBPL connector
overlay, and build the custom API/background image. Never hand-edit the ignored
checkout. Only the API/background image needs connector code; only the
background worker receives the read-only VBPL export mount.

```powershell
$env:ONYX_WEB_UI_PORT = '3001'
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
```

The UI is available only on localhost at `http://127.0.0.1:3001` by default.
Set `ONYX_WEB_UI_PORT` in the shell or the untracked repository `.env` to bind a
different localhost port. The API health endpoint is `http://127.0.0.1:8080/health`.

On first use of the current direct publisher, complete the basic-auth setup in
the UI and create an Onyx API key. Store it only in the untracked repository
`.env`:

```dotenv
VBPL_KB_ONYX_API_KEY=replace-with-local-onyx-api-key
VBPL_KB_ONYX_BASE_URL=http://api_server:8080
```

The current pipeline Compose service joins the `vbpl-onyx_default` network and
resolves `api_server` internally. Start Onyx before running the daily worker:

```powershell
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
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
