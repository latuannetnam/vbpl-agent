[CmdletBinding()]
param(
    [int]$Port = 0,
    [string]$Domain = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH. Please install ngrok or add it to PATH."
    }
}

Require-Command ngrok

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

# Resolve port: 1) explicit -Port argument, 2) $env:ONYX_WEB_UI_PORT, 3) ONYX_WEB_UI_PORT in .env, 4) fallback to 3001
if ($Port -le 0) {
    if ($env:ONYX_WEB_UI_PORT -and ($env:ONYX_WEB_UI_PORT -match '^\d+$')) {
        $Port = [int]$env:ONYX_WEB_UI_PORT
    } else {
        $envFile = Join-Path $projectRoot ".env"
        if (Test-Path -LiteralPath $envFile) {
            $envLines = Get-Content -LiteralPath $envFile -ErrorAction SilentlyContinue
            foreach ($line in $envLines) {
                $trimmed = $line.Trim()
                if ($trimmed -and -not $trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
                    $parts = $trimmed.Split("=", 2)
                    $key = $parts[0].Trim()
                    $val = $parts[1].Trim().Trim('"').Trim("'")
                    if ($key -eq "ONYX_WEB_UI_PORT" -and $val -match '^\d+$') {
                        $Port = [int]$val
                        break
                    }
                }
            }
        }
    }
}

if ($Port -le 0) {
    $Port = 3001
}

Write-Host "Checking local Onyx UI status on port $Port..." -ForegroundColor Cyan
try {
    $healthCheck = Invoke-WebRequest -Uri "http://127.0.0.1:$Port" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
    Write-Host "Onyx UI is active at http://127.0.0.1:$Port" -ForegroundColor Green
} catch {
    Write-Host "Warning: Could not reach Onyx UI at http://127.0.0.1:$Port. Ensure Onyx stack is started (`.\scripts\start-onyx.ps1`)." -ForegroundColor Yellow
}

# Check if ngrok tunnel is already active
$tunnelApiUrl = "http://127.0.0.1:4040/api/tunnels"
$existingTunnels = $null
try {
    $apiResp = Invoke-RestMethod -Uri $tunnelApiUrl -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($apiResp -and $apiResp.tunnels) {
        $existingTunnels = $apiResp.tunnels
    }
} catch {
    # Tunnel API not yet running
}

if ($existingTunnels) {
    Write-Host "`nAn active ngrok tunnel process was detected:" -ForegroundColor Green
    foreach ($tunnel in $existingTunnels) {
        Write-Host " -> Public URL: $($tunnel.public_url)  ==> $($tunnel.config.addr)" -ForegroundColor Yellow
    }
    Write-Host "To stop the active ngrok tunnel, run: Stop-Process -Name ngrok -Force" -ForegroundColor Gray
    exit 0
}

Write-Host "`nStarting ngrok tunnel for port $Port..." -ForegroundColor Cyan

$ngrokArgs = @("http", "$Port")
if ($Domain) {
    $ngrokArgs += @("--url", $Domain)
}

# Launch ngrok as a background process
$process = Start-Process -FilePath "ngrok" -ArgumentList $ngrokArgs -PassThru -NoNewWindow

Write-Host "Waiting for ngrok tunnel initialization..." -ForegroundColor Gray
$publicUrl = $null
$maxRetries = 10

for ($i = 1; $i -le $maxRetries; $i++) {
    Start-Sleep -Seconds 1
    try {
        $apiResp = Invoke-RestMethod -Uri $tunnelApiUrl -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($apiResp -and $apiResp.tunnels -and $apiResp.tunnels.Count -gt 0) {
            $publicUrl = $apiResp.tunnels[0].public_url
            break
        }
    } catch {
        # Retry loop
    }
}

if ($publicUrl) {
    Write-Host "`n==========================================================" -ForegroundColor Green
    Write-Host " Onyx UI is now publicly accessible via ngrok:" -ForegroundColor Green
    Write-Host " Public URL: $publicUrl" -ForegroundColor Yellow
    Write-Host " Local Endpoint: http://127.0.0.1:$Port" -ForegroundColor Gray
    Write-Host " Tunnel API: http://127.0.0.1:4040" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "To stop ngrok: Stop-Process -Name ngrok -Force`n" -ForegroundColor Gray
} else {
    Write-Host "ngrok started (PID: $($process.Id)), but could not query public URL from http://127.0.0.1:4040/api/tunnels." -ForegroundColor Yellow
    Write-Host "Inspect local tunnel dashboard at http://127.0.0.1:4040" -ForegroundColor Gray
}
