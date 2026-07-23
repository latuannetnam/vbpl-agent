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

# Resolve port and token:
# Priority for Port: 1) explicit -Port argument, 2) $env:ONYX_WEB_UI_PORT, 3) ONYX_WEB_UI_PORT in .env, 4) fallback to 3001
# Priority for Token: 1) explicit -Token argument, 2) $env:CLOUDFLARE_TUNNEL_TOKEN, 3) CLOUDFLARE_TUNNEL_TOKEN in .env
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

# Check if cloudflared process is already running
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
