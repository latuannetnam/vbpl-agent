# Cloudflare Tunnel Setup Script Design

Date: 2026-07-23  
Status: Approved  

## Goal
Provide a PowerShell setup script (`scripts/start-cloudflare-tunnel.ps1`) to expose the local Onyx Web UI endpoint via Cloudflare Tunnel (`cloudflared`). The script reads the target Onyx port and tunnel parameters from `.env` (or command-line overrides) and supports both token-authenticated tunnels (Cloudflare Zero Trust) and Quick Tunnels (`trycloudflare.com`).

## Architecture & Configuration

### 1. Environment Variables (`.env` and `.env.example`)
The script reads settings from `.env` at the project root:
- `ONYX_WEB_UI_PORT`: Local port where Onyx UI is running (default: `3001`).
- `CLOUDFLARE_TUNNEL_TOKEN`: Optional Cloudflare Zero Trust tunnel token.

### 2. Script Interface (`scripts/start-cloudflare-tunnel.ps1`)
```powershell
param(
    [int]$Port = 0,
    [string]$Token = "",
    [switch]$Quick
)
```

### 3. Execution Flow
1. **Dependency Check:** Validates `cloudflared` availability on `PATH`. Displays clear installation steps (`winget install Cloudflare.cloudflared`) if missing.
2. **Environment Resolution:**
   - Priority for `$Port`: `-Port` argument > `$env:ONYX_WEB_UI_PORT` > `.env` (`ONYX_WEB_UI_PORT`) > default `3001`.
   - Priority for `$Token`: `-Token` argument > `$env:CLOUDFLARE_TUNNEL_TOKEN` > `.env` (`CLOUDFLARE_TUNNEL_TOKEN`).
3. **Local Onyx Health Check:** Performs an HTTP request to `http://127.0.0.1:$Port` to verify the Onyx stack is active, printing a warning if unreadable.
4. **Existing Tunnel Detection:** Checks if `cloudflared` is already running to avoid duplicate background tunnel processes.
5. **Launch Mode Selection:**
   - **Token Mode:** If `$Token` is provided and `$Quick` is `$false`, runs `cloudflared tunnel run --token <Token>`.
   - **Quick Mode:** If `$Token` is empty or `$Quick` is `$true`, runs `cloudflared tunnel --url http://127.0.0.1:$Port`.
6. **URL Reporting:** Monitors output stream or metrics log to display the public URL (e.g. `https://xxxx.trycloudflare.com`) and process status.

## Verification Plan
1. Validate script execution when `cloudflared` is missing (verify error output).
2. Validate Quick Tunnel mode when no token is present in `.env`.
3. Validate Token Mode when token is provided in `.env`.
4. Verify local port resolution from `.env` (`ONYX_WEB_UI_PORT`).
