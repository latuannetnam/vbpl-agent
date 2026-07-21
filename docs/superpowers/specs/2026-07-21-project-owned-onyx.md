# Project-owned Onyx local deployment

## Purpose

Provide a repeatable local Onyx Standard deployment owned by this repository for
the VBPL knowledge-base pipeline.  The deployment supports the Onyx Search and
Chat UI while making Onyx's ingestion API the pipeline's source-of-truth target.

## Local state and source boundary

- The official `onyx-dot-app/onyx` repository is cloned below `.onyx/onyx`.
- `.onyx/` is ignored by Git. It includes the upstream source checkout, generated
  environment file, and all local deployment state.
- The repository tracks only the PowerShell lifecycle script, a Compose override
  template, and operational documentation. No passwords, API keys, or Onyx data
  are committed.

## Lifecycle script

`scripts/start-onyx.ps1` is idempotent and performs the following work:

1. Require Docker Compose and Git.
2. Stop the known legacy Compose project named `onyx`, if it is running.
3. Clone the official Onyx repository into `.onyx/onyx` when absent; otherwise
   retain the existing checkout rather than silently changing its version.
4. Generate the minimal local Onyx `.env` only when it does not already exist.
5. Copy the tracked Compose override into the upstream deployment directory.
6. Start Onyx as Compose project `vbpl-onyx` with the `s3-filestore` profile.
7. Wait for the API health endpoint and report the local UI URL.

The script does not remove legacy volumes or images.  That data remains
recoverable until an operator removes it explicitly.

## Ports and configuration

The UI port is configurable with `ONYX_WEB_UI_PORT`, sourced from the caller's
environment or the repository `.env`; it defaults to `3001`. The Compose override
binds Nginx as `127.0.0.1:${ONYX_WEB_UI_PORT}:80`, so the UI is not exposed on the
LAN. The API remains published on localhost for setup and diagnostics while the
pipeline uses the internal Docker network.

The override also normalizes the mounted Nginx startup script at container start
to remove Windows CRLF characters. This avoids the known shell interpreter error
when the upstream source is checked out on Windows.

## Pipeline integration

`docker-compose.vbpl.yml` joins the external network created by the Onyx Compose
project (`vbpl-onyx_default`).  The pipeline is configured to reach
`http://api_server:8080` on that network. Its Onyx credential and exact ingestion,
deletion, search, and health paths remain explicit environment settings.

The checked-in environment example provides the UI-port setting and documented
Onyx route defaults, but leaves the API key empty. Operators create the key in the
local Onyx UI and store it only in their untracked `.env`.

## Acceptance criteria

- Running `scripts/start-onyx.ps1` from the repository starts `vbpl-onyx` and
  stops the prior `onyx` Compose project without deleting its data.
- `http://127.0.0.1:${ONYX_WEB_UI_PORT}` responds through the Onyx Nginx UI.
- `http://127.0.0.1:8080/health` responds successfully after startup.
- `docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline` can resolve
  `api_server` through the `vbpl-onyx_default` network.
- `.onyx/` and generated secrets are excluded from Git status.
