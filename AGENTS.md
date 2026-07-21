# VBPL Legal Knowledge Base: Agent Guide

## Purpose and authoritative references

This repository builds an internal Vietnamese legal knowledge base. Treat these
documents as the source for design and operation; update them when behavior or
operations change:

- `README.md` — project overview and local developer entry points.
- `docs/operations.md` — pipeline, Docker, and recovery runbook.
- `docs/onyx-agent-setup.md` — Onyx Search/Chat and Legal Research Agent setup.
- `docs/superpowers/specs/2026-07-21-vbpl-legal-knowledge-base-design.md` —
  approved Release 1 architecture and legal-safety requirements.
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
- Do not publish or promote a partial, unverified, stale, or schema-invalid
  revision. Preserve the previous active corpus when a run is blocked.
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
- The pipeline joins the project-owned `vbpl-onyx_default` network and normally
  reaches Onyx at `http://api_server:8080` from inside Docker. Do not replace
  that internal address with a host UI URL.
- The UI host port is controlled by `ONYX_WEB_UI_PORT` (default `3001`), while
  the local API health endpoint is `http://127.0.0.1:8080/health`.

## Operating the project-owned Onyx stack

Start or update Onyx using the repository script:

```powershell
.\scripts\start-onyx.ps1
```

The upstream checkout lives in ignored `.onyx/onyx`; do not commit it. The
script manages the `vbpl-onyx` Compose project and safely replaces the legacy
`onyx` project when applicable. To stop the current project-owned stack without
removing its data:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```

## Operating the ingestion worker

After Python or Dockerfile changes, rebuild before `docker compose run`; `run`
does not rebuild the image automatically:

```powershell
docker compose -f docker-compose.vbpl.yml build vbpl-pipeline
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

For direct debugging, use the CLI stages with an explicit revision:

```powershell
uv run vbpl-kb crawl --db-path data/state.sqlite3 --revision vbpl-YYYY-MM-DD
uv run vbpl-kb publish --db-path data/state.sqlite3 --revision vbpl-YYYY-MM-DD
uv run vbpl-kb status --db-path data/state.sqlite3
```

The Compose worker writes progress to stdout. For a detached service, inspect
its logs using `docker compose -f docker-compose.vbpl.yml logs -f vbpl-pipeline`.
When an old image is running, stop it, rebuild, and rerun the same revision; the
persisted state enables resume.

## Release boundaries

Release 1 is the internal Onyx Search UI, Chat UI, and scoped VBPL Legal
Research Agent over the verified corpus. Keep the agent restricted to that
corpus, require citations for substantive claims, and refuse unsupported
current-law conclusions. Claude Code, Codex, Antigravity, and other external
agent/MCP integrations are later-phase work and must consume Onyx as the source
of truth rather than independently crawling VBPL.
