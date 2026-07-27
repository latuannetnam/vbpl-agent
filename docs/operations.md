# VBPL Knowledge Base Operations Runbook

**Status:** Current
**Applies to:** Local Docker lifecycle, scheduled daily pipeline runs, PostgreSQL migration, multi-view exports, observability, and recovery.
**Use for:** Starting Onyx, running PostgreSQL migrations, executing `publish.py`, verifying OpenSearch Schema-v2 completeness, and recovering safely from failed runs.
**Do not use for:** Choosing code architecture, changing legal-data policy, or configuring the running Onyx Legal Agent.

For component boundaries and connector contracts, read the
[architecture](architecture.md). For provenance, status, promotion, and
data-retention rules, read the [legal-data policy](legal-data-policy.md).

## Operational boundary

The pipeline uses content-addressed raw evidence (`data/evidence/sha256/`), a canonical database (`vbpl-db` / PostgreSQL), immutable multi-resolution sharded releases (`data/exports/releases/<release-id>/`), and a project-owned Onyx stack. The daily job performs an incremental catalog scan and requires two consecutive complete scans before tombstoning. Connector polling uses `from_beginning=False`. The daily job leaves the prior active release and indexed corpus available when source validation or connector indexing fails.

## Running the Pipeline via Docker Compose

To execute the data pipeline inside Docker containers:

1. **Start the Canonical PostgreSQL Database (`vbpl-db`)**:
   ```powershell
   docker compose -f docker-compose.vbpl.yml up -d vbpl-db
   ```

2. **Run Database Migrations (`vbpl-migrate`)**:
   ```powershell
   docker compose -f docker-compose.vbpl.yml run --rm vbpl-migrate
   ```

3. **Run the Daily Pipeline Container (`vbpl-pipeline`)**:
   ```powershell
   docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
   ```

## Running CLI commands locally

1. **Run Database Migrations (Alembic)**:
   ```powershell
   uv run alembic upgrade head
   ```

2. **Publish Multi-Resolution Release**:
   ```powershell
   uv run python publish.py --revision rev-$(Get-Date -Format 'yyyyMMdd')
   ```

3. **Verify Schema-v2 OpenSearch Metadata Completeness**:
   ```powershell
   uv run python -c "import json, random, subprocess, sys, pathlib; sys.stdout.reconfigure(encoding='utf-8'); act = json.loads(pathlib.Path('data/exports/active-release.json').read_text()); shard = pathlib.Path('data/exports/releases') / act['release_id'] / 'current' / 'documents-00000.jsonl'; lines = open(shard, encoding='utf-8').readlines()[:100]; ids = [json.loads(l)['metadata']['official_source_id'] for l in lines if 'official_source_id' in json.loads(l)['metadata']]; sample_ids = random.sample(list(set(ids)), 10); script = open('scripts/verify-schema-v2-index.py', encoding='utf-8').read(); cmd = ['docker', 'exec', '-i', 'vbpl-onyx-background-1', 'python', '-', *sample_ids]; res = subprocess.run(cmd, input=script, capture_output=True, text=True, encoding='utf-8'); print(res.stdout)"
   ```

## Project-owned local Onyx

Start the project-owned local Onyx CE stack from the repository root:

```powershell
$env:ONYX_WEB_UI_PORT = '3001'
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
```

The startup script calls `scripts/bootstrap-onyx.ps1` to verify the pinned
upstream revision, apply the committed overlay, and build the custom images for
multi-resolution connectors (`vbpl_current`, `vbpl_history`, `vbpl_evidence`).
The UI is available at `http://127.0.0.1:3001` by default and the local API
health endpoint is `http://127.0.0.1:8080/health`.

To stop the project-owned stack without deleting data:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```
