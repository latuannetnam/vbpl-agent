# VBPL Legal Knowledge Base: Coding-Agent Guide

**Status:** Current
**Applies to:** Codex, Claude Code, and maintainers changing this repository.
**Use for:** First-read guardrails, task routing, and required verification before repository changes.
**Do not use for:** Onyx Legal Agent runtime configuration, daily operator recovery steps, or historical design decisions.

## Project boundary

This repository builds an internal Vietnamese legal knowledge base. Official
VBPL API and canonical-page evidence are authoritative. The pipeline acquires
and validates that evidence; Onyx is the internal indexing, retrieval, and chat
interface. The Hugging Face dataset is bootstrap or coverage-comparison input
only.

## Read the current document for the task

| Task | Read first | Main locations |
| --- | --- | --- |
| Crawl, schema, normalization, authority hierarchy, legal status, or references | [Legal-data policy](docs/legal-data-policy.md), [architecture](docs/architecture.md) | `src/vbpl_kb/`, `tests/` |
| Export, release promotion, or connector input | [Legal-data policy](docs/legal-data-policy.md), [architecture](docs/architecture.md) | `publish.py`, `releases.py`, `state.py` |
| Onyx connector, overlay, Compose, or bootstrap | [Architecture](docs/architecture.md), [operations](docs/operations.md) | `infra/onyx/`, `scripts/`, Compose files |
| Daily execution, Docker, incident, or recovery | [Operations](docs/operations.md) | `scripts/`, Compose files |
| Onyx Legal Agent UI configuration | [Onyx agent setup](docs/onyx-agent-setup.md) | Runtime administration only |

Read [the development workflow](docs/development-workflow.md) for every
change. Read the focused existing tests before modifying crawler, normalization,
reference, state, release, connector, or publication behavior.

## Non-negotiable rules

- Preserve official source URL, legal status, verification time, corpus
  revision, provision structure, and raw evidence for every indexed instrument.
- Use `effStatus` or verified official canonical-page evidence for legal
  status; never infer legal force from editorial fields.
- Never promote partial, schema-invalid, or checksum-invalid releases. Keep the
  prior active export when a candidate is blocked.
- Keep unresolved legal-effect relationships unresolved unless explicit official
  evidence establishes them.
- Never use stale, failed, absent, expired, suspended, or conflicting evidence
  for a current-law claim.
- Do not delete `data/state.sqlite3`, `data/raw`, or a Docker volume merely to
  recover a crawl. A full recrawl needs explicit user approval.
- Do not commit `.env`, API keys, raw snapshots, database files, generated Onyx
  configuration, or untracked edits under `.onyx/onyx`.
- Do not add a production dependency on the diagnostic direct-ingestion path;
  the daily path uses the validated export and persistent connector.

## Safe development loop

1. Inspect the working tree and preserve unrelated changes.
2. Read the applicable current document and focused tests.
3. Add or update a focused regression test before production behavior changes.
4. Make the smallest coherent change and update the canonical document that
   owns changed behavior or operations.
5. Run focused tests, then the full verification set.

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Historical records in `docs/superpowers/` explain prior decisions but are not
current implementation instructions. Use them only when a current document
explicitly names them as background.

## Workspace-Scoped MCP Configuration

When adding workspace-scoped (project-local) MCP servers for Antigravity IDE:
1. **Plugin Directory Structure**:
   Create a dedicated plugin folder at `.agents/plugins/<plugin-name>/` containing:
   - `plugin.json`:
     ```json
     { "name": "<plugin-name>" }
     ```
   - `mcp_config.json`:
     ```json
     {
       "mcpServers": {
         "<server-id>": {
           "serverUrl": "http://127.0.0.1:<port>/",
           "url": "http://127.0.0.1:<port>/",
           "headers": {
             "Authorization": "Bearer <TOKEN>"
           }
         }
       }
     }
     ```
2. **Plugin Registration**:
   Register the plugin entry in `.agents/plugins.json`:
   ```json
   {
     "entries": [
       { "path": ".agents/plugins/<plugin-name>" }
     ]
   }
   ```
3. **Security & Git Invariant**:
   Never commit API tokens to source control. Always verify `.gitignore` includes `.agents/plugins/` (or token-bearing configuration files).
