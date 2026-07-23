# Cloudflare Tunnel Setup Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `scripts/start-cloudflare-tunnel.ps1` to expose local Onyx endpoint via Cloudflare Tunnel using port and token settings from `.env`.

**Architecture:** PowerShell script that parses `.env` for `ONYX_WEB_UI_PORT` and `CLOUDFLARE_TUNNEL_TOKEN`, checks for `cloudflared` executable, verifies local Onyx service health, and launches either an authenticated Zero Trust tunnel or a Quick Tunnel (`trycloudflare.com`).

**Tech Stack:** PowerShell 7 / Windows PowerShell, `cloudflared` CLI.

## Global Constraints

- Must follow PowerShell strict mode and error handling conventions used in `scripts/start-ngrok.ps1`.
- Preserve existing `.env` variables and do not commit sensitive keys or `.env` file changes to git.
- Support both `-Port`, `-Token`, and `-Quick` flags on the script CLI.

---

### Task 1: Update `.env.example`

**Files:**
- Modify: `.env.example`

**Interfaces:**
- Produces: `CLOUDFLARE_TUNNEL_TOKEN` documentation entry in `.env.example`.

- [ ] **Step 1: Edit `.env.example` to add Cloudflare Tunnel settings**

Add the following section at the bottom of `.env.example`:
```env
# Cloudflare Tunnel Configuration (Optional)
# If set, scripts/start-cloudflare-tunnel.ps1 will use token mode.
# If empty, scripts/start-cloudflare-tunnel.ps1 will default to Quick Tunnel mode (trycloudflare.com).
CLOUDFLARE_TUNNEL_TOKEN=
```

- [ ] **Step 2: Verify `.env.example` content**

Run: `Get-Content .env.example`
Expected: Section `CLOUDFLARE_TUNNEL_TOKEN=` appears at the end.

- [ ] **Step 3: Commit**

```powershell
git add .env.example
git commit -m "docs: add CLOUDFLARE_TUNNEL_TOKEN to .env.example"
```

---

### Task 2: Create `scripts/start-cloudflare-tunnel.ps1`

**Files:**
- Create: `scripts/start-cloudflare-tunnel.ps1`

**Interfaces:**
- Consumes: `ONYX_WEB_UI_PORT` and `CLOUDFLARE_TUNNEL_TOKEN` from `.env` or script arguments `-Port`, `-Token`, `-Quick`.
- Produces: Executable background `cloudflared` process tunneling to local Onyx endpoint.

- [ ] **Step 1: Create `scripts/start-cloudflare-tunnel.ps1`**

Write the following code into `scripts/start-cloudflare-tunnel.ps1`:

```powershell
[CmdletBinding()]
param(
    [int]$Port = 0,
    [string]$Token = "",
    [switch]$Quick
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "Error: Required command '$Name' was not found on PATH." -ForegroundColor Red
        Write-Host "To install cloudflared on Windows using winget:" -ForegroundColor Yellow
        Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor Cyan
        Write-Host "Or download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" -ForegroundColor Gray
        throw "Required command '$Name' was not found on PATH."
    }
}

Require-Command cloudflared

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

# Resolve port: 1) explicit -Port argument, 2) $env:ONYX_WEB_UI_PORT, 3) ONYX_WEB_UI_PORT in .env, 4) fallback to 3001
$envToken = ""

$envFile = Join-Path $projectRoot ".env"
if (Test-Path -LiteralPath $envFile) {
    $envLines = Get-Content -LiteralPath $envFile -ErrorAction SilentlyContinue
    foreach ($line in $envLines) {
        $trimmed = $line.Trim()
        if ($trimmed -and -not $trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
            $parts = $trimmed.Split("=", 2)
            $key = $parts[0].Trim()
            $val = $parts[1].Trim().Trim('"').Trim("'")
            if ($key -eq "ONYX_WEB_UI_PORT" -and $Port -le 0 -and $val -match '^\d+$') {
                $Port = [int]$val
            }
            if ($key -eq "CLOUDFLARE_TUNNEL_TOKEN" -and -not $Token) {
                $envToken = $val
            }
        }
    }
}

if ($Port -le 0) {
    if ($env:ONYX_WEB_UI_PORT -and ($env:ONYX_WEB_UI_PORT -match '^\d+$')) {
        $Port = [int]$env:ONYX_WEB_UI_PORT
    } else {
        $Port = 3001
    }
}

if (-not $Token) {
    if ($env:CLOUDFLARE_TUNNEL_TOKEN) {
        $Token = $env:CLOUDFLARE_TUNNEL_TOKEN
    } else {
        $Token = $envToken
    }
}

Write-Host "Checking local Onyx UI status on port $Port..." -ForegroundColor Cyan
try {
    $healthCheck = Invoke-WebRequest -Uri "http://127.0.0.1:$Port" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
    Write-Host "Onyx UI is active at http://127.0.0.1:$Port" -ForegroundColor Green
} catch {
    Write-Host "Warning: Could not reach Onyx UI at http://127.0.0.1:$Port. Ensure Onyx stack is started (`.\scripts\start-onyx.ps1`)." -ForegroundColor Yellow
}

# Check if cloudflared tunnel process is already running
$runningProcesses = Get-Process -Name cloudflared -ErrorAction SilentlyContinue
if ($runningProcesses) {
    Write-Host "`nAn active cloudflared process was detected (PID: $($runningProcesses[0].Id))." -ForegroundColor Yellow
    Write-Host "To stop existing tunnel: Stop-Process -Name cloudflared -Force" -ForegroundColor Gray
}

if ($Token -and -not $Quick) {
    Write-Host "`nStarting Cloudflare Tunnel in Token Mode..." -ForegroundColor Cyan
    Write-Host "Local Target: http://127.0.0.1:$Port" -ForegroundColor Gray
    
    $argsList = @("tunnel", "run", "--token", $Token)
    $process = Start-Process -FilePath "cloudflared" -ArgumentList $argsList -PassThru -NoNewWindow
    
    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host " Cloudflare Tunnel started in Token Mode (PID: $($process.Id))" -ForegroundColor Green
    Write-Host " Local Endpoint: http://127.0.0.1:$Port" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "To stop tunnel: Stop-Process -Name cloudflared -Force`n" -ForegroundColor Gray
} else {
    Write-Host "`nStarting Cloudflare Quick Tunnel for port $Port..." -ForegroundColor Cyan
    Write-Host "Target: http://127.0.0.1:$Port" -ForegroundColor Gray

    $argsList = @("tunnel", "--url", "http://127.0.0.1:$Port")
    $process = Start-Process -FilePath "cloudflared" -ArgumentList $argsList -PassThru -NoNewWindow

    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host " Cloudflare Quick Tunnel process started (PID: $($process.Id))" -ForegroundColor Green
    Write-Host " Local Endpoint: http://127.0.0.1:$Port" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "Check console output above or cloudflared log for your *.trycloudflare.com URL." -ForegroundColor Yellow
    Write-Host "To stop tunnel: Stop-Process -Name cloudflared -Force`n" -ForegroundColor Gray
}
```

- [ ] **Step 2: Test script syntax in PowerShell**

Run: `powershell -Command "AST = [System.Management.Automation.Language.Parser]::ParseFile('scripts/start-cloudflare-tunnel.ps1', [ref]\$null, [ref]\$null); if (\$AST) { 'Syntax OK' }"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```powershell
git add scripts/start-cloudflare-tunnel.ps1
git commit -m "feat: add scripts/start-cloudflare-tunnel.ps1 script"
```

---

### Task 3: Update Documentation (`docs/operations.md` and `README.md`)

**Files:**
- Modify: `docs/operations.md`
- Modify: `README.md`

- [ ] **Step 1: Add Cloudflare Tunnel instructions to `docs/operations.md`**

In `docs/operations.md`, add a section under local access/tunnels for Cloudflare Tunnel:
```markdown
### Exposing Onyx UI via Cloudflare Tunnel

To make the Onyx Web UI accessible remotely using Cloudflare Tunnel:

```powershell
.\scripts\start-cloudflare-tunnel.ps1
```

- **Quick Tunnel (Default):** If `CLOUDFLARE_TUNNEL_TOKEN` is not set in `.env`, a quick tunnel will launch pointing to `http://127.0.0.1:3001` generating a `trycloudflare.com` public URL.
- **Token Mode:** Set `CLOUDFLARE_TUNNEL_TOKEN=<your_token>` in `.env` to route through your Cloudflare Zero Trust domain.
- **Custom Options:** You can pass `-Port 3001`, `-Token "<token>"`, or `-Quick`.
```

- [ ] **Step 2: Update `README.md` script reference table**

Add `start-cloudflare-tunnel.ps1` to the quick reference section in `README.md`.

- [ ] **Step 3: Commit**

```powershell
git add docs/operations.md README.md
git commit -m "docs: add Cloudflare Tunnel usage instructions to operations.md and README.md"
```
