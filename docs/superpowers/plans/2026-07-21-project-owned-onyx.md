# Project-owned Onyx Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a reproducible, project-owned Onyx Docker deployment that exposes a configurable localhost UI and is reachable by the VBPL pipeline through Docker networking.

**Architecture:** A PowerShell lifecycle script owns an ignored `.onyx/onyx` clone of the official Onyx repository and starts it under Compose project `vbpl-onyx`. A checked-in Compose override binds the Nginx UI to the configurable localhost port and fixes the Windows CRLF startup issue. The existing one-shot pipeline joins the external Onyx network and uses the internal API hostname.

**Tech Stack:** PowerShell 7, Docker Compose, Git, official Onyx Standard Compose deployment, Python/pytest configuration tests.

## Global Constraints

- Clone official Onyx source only below `.onyx/onyx`; ignore all of `.onyx/` in Git.
- Do not commit generated Onyx environment files, credentials, source code, images, volumes, or indexes.
- Start the new stack with Compose project name `vbpl-onyx` and profile `s3-filestore`.
- Stop only the known legacy Compose project named `onyx`; never remove its volumes or images.
- Bind the UI to `127.0.0.1:${ONYX_WEB_UI_PORT}`, defaulting to `3001`.
- Keep the pipeline’s Onyx API key and exact routes as explicit environment variables.
- The pipeline must use `http://api_server:8080` through external Docker network `vbpl-onyx_default`.

---

## File structure

- Create: `.onyx/` ignore rule in `.gitignore` — excludes all local Onyx source and state.
- Create: `infra/onyx/docker-compose.vbpl-ui.yml` — tracked Nginx port and Windows-compatible startup override.
- Create: `scripts/start-onyx.ps1` — clone, legacy shutdown, compose startup, and health wait lifecycle.
- Modify: `.env.example` — documents `ONYX_WEB_UI_PORT`, internal Onyx base URL, and verified ingestion API paths.
- Modify: `docker-compose.vbpl.yml` — attaches the pipeline to the external Onyx Docker network.
- Modify: `docs/operations.md` — gives local startup, initial setup, API-key, daily run, and shutdown instructions.
- Create: `tests/test_onyx_deployment.py` — statically validates tracked lifecycle/configuration contracts without Docker.

### Task 1: Add testable deployment assets

**Files:**
- Create: `tests/test_onyx_deployment.py`
- Create: `infra/onyx/docker-compose.vbpl-ui.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: repository root paths.
- Produces: a tracked `infra/onyx/docker-compose.vbpl-ui.yml` with `${ONYX_WEB_UI_PORT:-3001}` and a test proving ignored local state.

- [ ] **Step 1: Write the failing deployment-contract tests**

```python
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_local_onyx_directory_is_ignored() -> None:
    assert ".onyx/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_ui_override_binds_configurable_localhost_port() -> None:
    compose = (ROOT / "infra/onyx/docker-compose.vbpl-ui.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:${ONYX_WEB_UI_PORT:-3001}:80"' in compose
    assert "tr -d '\\\\015'" in compose
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_onyx_deployment.py -q`

Expected: FAIL because the override and ignore rule do not yet exist.

- [ ] **Step 3: Add the minimal ignored-state and UI override assets**

Append this line to `.gitignore`:

```gitignore
.onyx/
```

Create `infra/onyx/docker-compose.vbpl-ui.yml`:

```yaml
services:
  nginx:
    ports: !override
      - "127.0.0.1:${ONYX_WEB_UI_PORT:-3001}:80"
    command: >
      /bin/sh -c "rm -f /etc/nginx/conf.d/default.conf
      && cp -a /nginx-templates/. /etc/nginx/conf.d/
      && tr -d '\\015' < /etc/nginx/conf.d/run-nginx.sh > /tmp/run-nginx.sh
      && chmod +x /tmp/run-nginx.sh
      && /bin/sh /tmp/run-nginx.sh app.conf.template"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_onyx_deployment.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore infra/onyx/docker-compose.vbpl-ui.yml tests/test_onyx_deployment.py
git commit -m "feat: add local Onyx deployment assets"
```

### Task 2: Implement safe Onyx lifecycle management

**Files:**
- Create: `scripts/start-onyx.ps1`
- Modify: `tests/test_onyx_deployment.py`

**Interfaces:**
- Consumes: `ONYX_WEB_UI_PORT` from process environment or repository `.env` and `infra/onyx/docker-compose.vbpl-ui.yml`.
- Produces: `scripts/start-onyx.ps1`, callable with `pwsh -File scripts/start-onyx.ps1`, which starts `vbpl-onyx` and reports its UI address.

- [ ] **Step 1: Extend the failing tests for script safety and Compose identity**

```python
def test_start_script_uses_scoped_legacy_shutdown_and_project_name() -> None:
    script = (ROOT / "scripts/start-onyx.ps1").read_text(encoding="utf-8")
    assert "--project-name onyx down" in script
    assert "--project-name vbpl-onyx" in script
    assert "--profile s3-filestore up -d" in script
    assert "git clone --depth 1 https://github.com/onyx-dot-app/onyx.git" in script
    assert "Remove-Volume" not in script
    assert "docker volume rm" not in script
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_onyx_deployment.py -q`

Expected: FAIL because `scripts/start-onyx.ps1` does not exist.

- [ ] **Step 3: Implement the minimal lifecycle script**

Implement functions `Require-Command`, `Get-ProjectEnvironment`, `Wait-OnyxHealth`, and `Invoke-Compose`. The script must:

```powershell
$onyxRoot = Join-Path $PSScriptRoot "..\\.onyx\\onyx"
$composeDir = Join-Path $onyxRoot "deployment\\docker_compose"
$overrideSource = Join-Path $PSScriptRoot "..\\infra\\onyx\\docker-compose.vbpl-ui.yml"
$overrideTarget = Join-Path $composeDir "docker-compose.vbpl-ui.yml"

docker compose --project-name onyx down
docker compose --project-name vbpl-onyx `
  -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.vbpl-ui.yml `
  --profile s3-filestore up -d
```

Create `.onyx/onyx/deployment/docker_compose/.env` only when absent. It must set
`AUTH_TYPE=basic` and a cryptographically random `USER_AUTH_SECRET`; never print
the value. Copy the tracked override before startup. Wait up to 180 seconds for
`http://127.0.0.1:8080/health`, then print `http://127.0.0.1:$uiPort`.

- [ ] **Step 4: Run static tests and PowerShell parser validation**

Run:

```powershell
uv run pytest tests/test_onyx_deployment.py -q
pwsh -NoProfile -Command "[void][scriptblock]::Create((Get-Content scripts/start-onyx.ps1 -Raw))"
```

Expected: tests pass and PowerShell exits `0`.

- [ ] **Step 5: Commit**

```bash
git add scripts/start-onyx.ps1 tests/test_onyx_deployment.py
git commit -m "feat: add project-owned Onyx startup script"
```

### Task 3: Connect the daily pipeline to local Onyx

**Files:**
- Modify: `docker-compose.vbpl.yml`
- Modify: `.env.example`
- Modify: `tests/test_onyx_deployment.py`

**Interfaces:**
- Consumes: Docker network `vbpl-onyx_default` created by Task 2.
- Produces: a `vbpl-pipeline` service on that network with internal Onyx base URL and explicit verified endpoint defaults.

- [ ] **Step 1: Extend failing configuration tests**

```python
def test_pipeline_uses_the_project_owned_onyx_network() -> None:
    compose = (ROOT / "docker-compose.vbpl.yml").read_text(encoding="utf-8")
    assert "http://api_server:8080" in compose
    assert "name: vbpl-onyx_default" in compose
    assert "external: true" in compose


def test_environment_example_exposes_ui_port_and_verified_routes() -> None:
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ONYX_WEB_UI_PORT=3001" in env
    assert "VBPL_KB_ONYX_INGESTION_UPSERT_PATH=/onyx-api/ingestion" in env
    assert "VBPL_KB_ONYX_SEARCH_PATH=/admin/search" in env
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_onyx_deployment.py -q`

Expected: FAIL because the Compose network and environment defaults are missing.

- [ ] **Step 3: Update Compose and environment example**

Set the worker base URL and attach the network:

```yaml
    environment:
      - VBPL_KB_ONYX_BASE_URL=${VBPL_KB_ONYX_BASE_URL:-http://api_server:8080}
    networks:
      - onyx

networks:
  onyx:
    external: true
    name: vbpl-onyx_default
```

Add these safe defaults to `.env.example`:

```dotenv
ONYX_WEB_UI_PORT=3001
VBPL_KB_ONYX_BASE_URL=http://api_server:8080
VBPL_KB_ONYX_INGESTION_UPSERT_PATH=/onyx-api/ingestion
VBPL_KB_ONYX_INGESTION_DELETE_PATH=/onyx-api/ingestion/{document_id}
VBPL_KB_ONYX_SEARCH_PATH=/admin/search
VBPL_KB_ONYX_HEALTH_PATH=/health
```

Keep `VBPL_KB_ONYX_API_KEY` blank and require the operator to supply it.

- [ ] **Step 4: Verify static configuration and Compose rendering**

Run:

```powershell
uv run pytest tests/test_onyx_deployment.py -q
$env:VBPL_KB_ONYX_API_KEY='validation-only'; docker compose -f docker-compose.vbpl.yml config
```

Expected: tests pass and the rendered service includes `api_server:8080` plus
external network `vbpl-onyx_default`.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.vbpl.yml .env.example tests/test_onyx_deployment.py
git commit -m "feat: connect VBPL pipeline to local Onyx"
```

### Task 4: Document and verify the end-to-end local deployment

**Files:**
- Modify: `docs/operations.md`

**Interfaces:**
- Consumes: the lifecycle script from Task 2 and Compose configuration from Task 3.
- Produces: operator instructions for first-run setup, API-key storage, daily execution, and non-destructive shutdown.

- [ ] **Step 1: Add operations documentation**

Add a “Project-owned local Onyx” section containing these commands:

```powershell
$env:ONYX_WEB_UI_PORT = '3001'
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
# open http://127.0.0.1:3001, complete basic setup, then create an API key
```

Document storage of the generated API key in untracked `.env`, then run the
daily worker:

```powershell
docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline
```

Document a non-destructive shutdown:

```powershell
Push-Location .onyx/onyx/deployment/docker_compose
docker compose --project-name vbpl-onyx down
Pop-Location
```

- [ ] **Step 2: Start the project-owned stack and verify service health**

Run:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
Invoke-WebRequest http://127.0.0.1:8080/health -UseBasicParsing
Invoke-WebRequest "http://127.0.0.1:$env:ONYX_WEB_UI_PORT" -UseBasicParsing
docker compose ls
```

Expected: health and UI return HTTP `200`; Compose shows `vbpl-onyx` running and
the legacy `onyx` project stopped or absent.

- [ ] **Step 3: Verify pipeline network resolution without publishing records**

Run:

```powershell
docker compose -f docker-compose.vbpl.yml run --rm --entrypoint /bin/sh vbpl-pipeline -lc "getent hosts api_server && wget -qO- http://api_server:8080/health"
```

Expected: `api_server` resolves and its health response is successful.

- [ ] **Step 4: Run complete regression suite and inspect changes**

Run:

```powershell
uv run pytest -q
uv run ruff check .
uv run mypy src
git diff --check
git status --short
```

Expected: all tests, Ruff, mypy, and whitespace checks pass. `git status` does
not show `.onyx/` or generated credentials.

- [ ] **Step 5: Commit**

```bash
git add docs/operations.md
git commit -m "docs: document local Onyx operations"
```

## Self-review

Spec coverage: Task 1 covers ignored local source/state and Windows-compatible UI override. Task 2 covers clone, scoped legacy shutdown, persistent generated configuration, profile startup, and health reporting. Task 3 covers configurable UI documentation, internal pipeline networking, and explicit API routes. Task 4 covers operations, UI/API health, legacy replacement validation, network validation, and full regression verification.

Placeholder scan: no `TODO`, `TBD`, deferred implementation, or undefined interface references remain.

Type consistency: Task 2 produces the `vbpl-onyx` project and `vbpl-onyx_default` network consumed by Task 3. Task 3’s `api_server:8080` configuration is the host checked by Task 4.
