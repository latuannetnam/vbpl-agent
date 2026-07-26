# VBPL Knowledge Base Operations Runbook

**Status:** Current
**Applies to:** Local Docker lifecycle, scheduled daily pipeline runs, observability, and recovery.
**Use for:** Starting Onyx, running the pipeline, reading outcomes, and recovering safely from failed runs.
**Do not use for:** Choosing code architecture, changing legal-data policy, or configuring the running Onyx Legal Agent.

For component boundaries and connector contracts, read the
[architecture](architecture.md). For provenance, status, promotion, and
data-retention rules, read the [legal-data policy](legal-data-policy.md).

## Operational boundary

The pipeline uses persisted SQLite state, retained raw snapshots, immutable
export releases, and a project-owned Onyx stack. The daily job must leave the
prior active release and indexed corpus available when source validation or
connector indexing fails. Architecture details belong in the
[architecture](architecture.md); this runbook contains the commands and
recovery actions.

## Running CLI commands

Run commands through `uv run` from the repository root:

- **Status check** checks health and freshness of the active revision. It exits
  with code `2` when the release is stale or partial.

  ```powershell
  uv run vbpl-kb status --db-path data/state.sqlite3
  ```

- **Daily pipeline** discovers, fetches, normalizes, validates, exports, and
  requests connector indexing.

  ```powershell
  uv run vbpl-kb run-daily --db-path data/state.sqlite3
  ```

- **Manual crawl** runs only the checkpointed crawler for an explicit revision.

  ```powershell
  uv run vbpl-kb crawl --db-path data/state.sqlite3 --revision vbpl-2026-07-23
  ```

- **Reset and re-index Onyx vector store** drops current OpenSearch vector embeddings for the connector and re-indexes the promoted active release using `.env` settings (without re-crawling).

  ```powershell
  uv run python scripts/reset-and-reindex-onyx.py
  ```

## Docker Compose daily execution

The Compose worker is a one-shot scheduled job. Rebuild before `run`, because
`docker compose run` does not rebuild the image automatically:

```powershell
docker compose -f docker-compose.vbpl.yml build vbpl-pipeline
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

The worker streams crawl and export counts to stdout. For a detached invocation,
inspect its logs with:

```powershell
docker compose -f docker-compose.vbpl.yml logs -f vbpl-pipeline
```

Keep `VBPL_KB_ONYX_API_KEY` and `VBPL_KB_ONYX_CONNECTOR_ID` in the untracked
`.env` file. Do not print a resolved Compose environment or expose either
value in logs.

The pipeline does not expose public ports. Its data persists in the
`vbpl-pipeline-data` volume.

## Daily outcome and safe failure handling

`run-daily` performs an incremental catalog scan, fetching details only for new or changed documents. It requires two consecutive complete scans before declaring a missing document a tombstone. It validates and promotes a self-contained full release candidate plus a delta batch, and triggers connector delta polling with `from_beginning=False`. A blocked candidate leaves the active-release pointer unchanged. A connector failure preserves the previously indexed corpus; pending delta batches are retried automatically on subsequent runs without deleting state, raw snapshots, volumes, or the connector. Explicit full re-indexing using `scripts/reset-and-reindex-onyx.py` is reserved for index schema or normalizer compatibility upgrades.

## Project-owned local Onyx

Start the project-owned local Onyx CE stack from the repository root:

```powershell
$env:ONYX_WEB_UI_PORT = '3001'
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
```

The startup script calls `scripts/bootstrap-onyx.ps1` to verify the pinned
upstream revision, apply the committed overlay, and build the custom images.
The UI is available at `http://127.0.0.1:3001` by default and the local API
health endpoint is `http://127.0.0.1:8080/health`.

To stop the project-owned stack without deleting data:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```

### Exposing Onyx UI via Tunnels (Cloudflare & ngrok)

To expose the local Onyx UI for remote access:

- **Cloudflare Tunnel:**
  ```powershell
  .\scripts\start-cloudflare-tunnel.ps1
  ```
  *If `CLOUDFLARE_TUNNEL_TOKEN` is set in `.env`, token mode is used. Otherwise, it defaults to Quick Tunnel (`trycloudflare.com`).*

- **ngrok Tunnel:**
  ```powershell
  .\scripts\start-ngrok.ps1
  ```

## Chat and Legal Agent release surface

Release 1 exposes normal Onyx CE Chat and the scoped VBPL Legal Agent. Do not
configure or document a standalone Search Mode UI. The Legal Agent is limited to
the VBPL connector/document set and Internal Search; web search, code execution,
and external write actions remain disabled. Use [Onyx agent
setup](onyx-agent-setup.md) for required runtime grounding and citation
configuration.
