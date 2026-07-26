# VBPL Legal Knowledge Base Pipeline

**Status:** Current
**Applies to:** Developers and operators starting or maintaining the local VBPL knowledge-base stack.
**Use for:** Project orientation, prerequisites, current quick-start commands, and documentation discovery.
**Do not use for:** Detailed architecture contracts, legal-data policy interpretation, incident recovery, or Onyx Legal Agent configuration.

This project snapshots official Vietnamese legal databases, validates and
structures the records, publishes immutable verified releases with delta manifests, and makes them
searchable through an internal Onyx Community Edition deployment using incremental connector polling. Official VBPL
evidence remains authoritative; Onyx provides indexing, retrieval, and chat.

## Prerequisites

- Windows PowerShell, Docker Desktop, and `uv`.
- An untracked `.env` created from `.env.example`.
- A local Onyx API key and connector ID only when connector-trigger features
  require them. Never commit or print those values.

## Quick start

Install the locked Python environment:

```powershell
uv sync
```

Start or update the project-owned Onyx stack:

```powershell
.\scripts\start-onyx.ps1
```

Optionally expose Onyx via Cloudflare Tunnel:

```powershell
.\scripts\start-cloudflare-tunnel.ps1
```

Run the daily incremental pipeline (scans catalog metadata fingerprints, acquires new/changed details, exports delta release, and polls connector):

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run vbpl-kb run-daily --db-path data/state.sqlite3
uv run vbpl-kb status --db-path data/state.sqlite3
uv run pytest -q
uv run ruff check .
uv run mypy src
```

For the Docker-first daily execution and recovery procedure, use the
[operations runbook](docs/operations.md).

## Documentation map

- [Coding-agent guide](AGENTS.md) — task routing, safety rules, and
  verification gate.
- [Architecture](docs/architecture.md) — boundaries, ownership, code map, and
  connector contract.
- [Development workflow](docs/development-workflow.md) — safe change and
  verification process.
- [Legal-data policy](docs/legal-data-policy.md) — provenance, status,
  promotion, and recovery rules.
- [Operations](docs/operations.md) — Docker lifecycle, daily execution,
  observability, and recovery.
- [Onyx agent setup](docs/onyx-agent-setup.md) — administrator configuration of
  the running legal-research agent.

Date-stamped material under `docs/superpowers/` is historical decision and
planning context. It is not the operational source of truth; use the current
documents above for work on this repository.
