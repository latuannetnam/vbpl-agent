# VBPL Legal Knowledge Base: Agent Guide

## Purpose and authoritative references

This repository builds an internal Vietnamese legal knowledge base. Treat these
documents as the source for design and operation; update them when behavior or
operations change:

- `README.md` — project overview and local developer entry points.
- `docs/operations.md` — pipeline, Docker, and recovery runbook.
- `docs/onyx-agent-setup.md` — Onyx CE Chat and VBPL Legal Agent setup.
- `docs/superpowers/specs/2026-07-22-vbpl-ce-custom-connector-design.md` —
  approved Release 1 target architecture and legal-safety requirements.
- `docs/superpowers/specs/2026-07-21-vbpl-legal-knowledge-base-design.md` —
  earlier architecture; the 2026-07-22 connector design supersedes it when
  the two conflict.
- `docs/superpowers/specs/2026-07-21-verified-vbpl-fallback.md` — policy for
  malformed official VBPL records.

The official VBPL service (`vbpl.vn` and its public gateway API) is the legal
authority. Onyx is the internal search, chat, and agent interface—not an
authority or a replacement crawler. The Hugging Face dataset is bootstrap or
coverage-comparison input only; it must never establish a document's current
legal status.

## Non-negotiable legal-data rules

- Every indexed instrument must retain its official source URL, legal status,
  verification time, corpus revision, and provision structure.
- Never infer legal force from editorial fields such as `status: Publish` or
  `reviewStatus`. Use `effStatus` or an explicitly verified official canonical
  page fallback.
- Do not promote a partial, schema-invalid, or checksum-invalid source release.
  Preserve the previous active export when a candidate is blocked. A document
  whose official status cannot be established may be indexed as `unknown` only
  after its raw evidence is retained; it must never support a current-law claim.
- Treat unresolved legal-effect relationships as unresolved. Only explicit
  official evidence may create amendment, replacement, or repeal edges.
- Never describe a document as currently effective when its verification is
  stale, failed, absent, expired, suspended, or conflicting.
- Do not delete `data/state.sqlite3`, `data/raw`, or the Docker volume merely
  to recover a crawl. The crawler is checkpointed and resumes the same
  revision, retrying missing detail snapshots. Delete data only for a deliberate
  full recrawl approved by the user.

## Local development workflow

1. Read the relevant specification and existing tests before changing crawler,
   normalization, reference, state, or publication behavior.
2. Add or update a focused regression test before changing production behavior,
   especially for an upstream VBPL schema variant or fallback case.
3. Run the full verification set before committing:

   ```powershell
   $env:UV_CACHE_DIR="$PWD\.uv-cache"
   uv run pytest -q
   uv run ruff check .
   uv run mypy src
   ```

4. Keep commits focused. Do not discard unrelated working-tree changes.

## Configuration and secrets

- Copy `.env.example` to the untracked `.env`; do not commit `.env`, API keys,
  generated Onyx configuration, raw snapshots, or database files.
- Keep `VBPL_KB_ONYX_API_KEY` secret. Never print it, run commands that dump
  the resolved Compose environment, or include it in logs, tests, docs, or
  commits.
- The current direct-publisher pipeline joins the project-owned
  `vbpl-onyx_default` network and normally reaches Onyx at
  `http://api_server:8080` from inside Docker. Do not replace that internal
  address with a host UI URL. The approved connector design removes this API
  dependency from the production daily path; do not add new production behavior
  that relies on the direct ingestion API.
- The UI host port is controlled by `ONYX_WEB_UI_PORT` (default `3001`), while
  the local API health endpoint is `http://127.0.0.1:8080/health`.

## Operating the project-owned Onyx stack

Start or update Onyx using the repository script:

```powershell
.\scripts\start-onyx.ps1
```

The upstream checkout lives in ignored `.onyx/onyx`; do not commit it. The
current script manages the `vbpl-onyx` Compose project and safely replaces the
legacy `onyx` project when applicable. The connector migration must use a
pinned upstream revision plus a committed project overlay/custom image; never
make untracked manual source edits under `.onyx/onyx`. To stop the current
project-owned stack without removing its data:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```

## Onyx Custom Connector & GPU Configuration Invariants

- Custom Onyx connectors (`VBPLExportConnector`) inheriting from `PollConnector` or `LoadConnector` MUST yield **batches of documents (`list[Document]`)** matching `self.batch_size` from `poll_source()` and `load_from_state()`. Yielding single `Document` instances breaks Onyx's batch separator and yields 0 queued batches.
- Do not filter out documents using `changed_after` in export connectors; active release manifests represent complete promoted snapshots and must yield all documents to Onyx.
- Custom connector sources (`vbpl_export`) MUST be registered in the web frontend overlay (`infra/onyx/overlay/web/src/lib/`):
  - `types.ts`: Add `VBPLExport = "vbpl_export"` to `ValidSources` and exclude `ValidSources.VBPLExport` in `ConfigurableSources`.
  - `sources.ts`: Add `vbpl_export` entry to `SOURCE_METADATA_MAP`.
  - `credentials.ts`: Add `vbpl_export: null` to `credentialTemplates`.
- `scripts/bootstrap-onyx.ps1` MUST include `web_server` in `docker compose build` (`build api_server background web_server`) to build the custom web UI image from overlay sources.
- Enable GPU acceleration for `indexing_model_server` in Compose override files (`infra/onyx/docker-compose.vbpl-connector.yml`):
  ```yaml
  indexing_model_server:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
  ```
- Tune `.env` for GPU indexing throughput with `DOC_EMBEDDING_BATCH_SIZE=32` and `CELERY_WORKER_DOCPROCESSING_CONCURRENCY=8`.

## Operating the ingestion worker

Always use Docker Compose as the default execution method for daily pipeline sync tasks. Rebuild before `docker compose run`; `run`
does not rebuild the image automatically:

```powershell
docker compose -f docker-compose.vbpl.yml build vbpl-pipeline
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

For direct debugging of the implementation, use the CLI commands with an
explicit revision. `publish-legacy` is a diagnostic direct-ingestion path;
the standard daily path is `run-daily` using `VBPL Export Connector`:

```powershell
uv run vbpl-kb crawl --db-path data/state.sqlite3 --revision vbpl-YYYY-MM-DD
uv run vbpl-kb run-daily --db-path data/state.sqlite3
uv run vbpl-kb status --db-path data/state.sqlite3
```

The Compose worker writes progress to stdout. For a detached service, inspect
its logs using `docker compose -f docker-compose.vbpl.yml logs -f vbpl-pipeline`.
When an old image is running, stop it, rebuild, and rerun the same revision; the
persisted state enables resume.

## Release boundaries

Release 1 is the internal Onyx CE Chat UI and scoped VBPL Legal Agent over the
verified corpus. Do not depend on the gated standalone Onyx Search Mode UI.
Keep the agent restricted to the VBPL connector/document set, require citations
for substantive claims, and refuse unsupported current-law conclusions. Claude
Code, Codex, Antigravity, and other external agent/MCP integrations are
later-phase work and must consume Onyx as the source of truth rather than
independently crawling VBPL.
