# VBPL Knowledge Base Development Workflow

**Status:** Current
**Applies to:** All repository code, test, infrastructure, and documentation changes.
**Use for:** Classifying a task, choosing current guidance, implementing safely, and reporting verification.
**Do not use for:** Daily operations or editing the running Onyx Legal Agent configuration.

## Start every task

Inspect the working tree first and preserve unrelated changes. Classify the task
before editing:

| Change | Read first | Likely locations |
| --- | --- | --- |
| Crawl, schemas, normalization, status, or references | [Legal-data policy](legal-data-policy.md), [architecture](architecture.md) | `src/vbpl_kb/`, `tests/` |
| Exports, release promotion, or connector input | [Legal-data policy](legal-data-policy.md), [architecture](architecture.md) | `publish.py`, `releases.py`, `repositories.py` |
| Connector, overlay, Compose, or bootstrap | [Architecture](architecture.md), [operations](operations.md) | `infra/onyx/`, `scripts/`, Compose files |
| Daily execution, Docker, incident, or recovery | [Operations](operations.md) | `scripts/`, Compose files |
| Onyx Legal Agent UI configuration | [Onyx agent setup](onyx-agent-setup.md) | Runtime administration only |

## Change loop

1. Read the applicable current documents and focused existing tests.
2. Add or update a focused regression test before changing production behavior.
3. Make the smallest coherent change that satisfies the test and preserves the
   legal-data policy.
4. Update the canonical document that owns any changed behavior or operation;
   use links rather than duplicate prose.
5. Run focused tests, then the required full verification set.
6. Report changed files, commands run, outcomes, and any deliberately
   unverified external boundary.

## Verification gate

Run these commands before committing:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Use Docker Compose as the default path for daily pipeline execution. Rebuild the
pipeline image before `docker compose run`, because `run` does not rebuild it.
Keep secrets out of commands, logs, tests, documentation, and commits.

## Current versus historical guidance

Use `AGENTS.md` and the current documents linked from it as implementation
instructions. Treat `docs/superpowers/specs/` and `docs/superpowers/plans/` as
historical records. Read one only when a current document explicitly directs you
to background for an unresolved design decision.
