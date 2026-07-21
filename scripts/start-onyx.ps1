[CmdletBinding()]
param(
    [ValidateRange(1, 1800)]
    [int]$HealthTimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Get-ProjectEnvironment {
    param([Parameter(Mandatory)][string]$ProjectRoot)

    $environment = @{}
    $environmentPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $environmentPath)) {
        return $environment
    }

    foreach ($line in Get-Content -LiteralPath $environmentPath) {
        if ($line -match '^\s*#' -or $line -notmatch '=') {
            continue
        }

        $name, $value = $line -split '=', 2
        $name = $name.Trim()
        if ($name) {
            $environment[$name] = $value.Trim().Trim('"').Trim("'")
        }
    }

    return $environment
}

function Stop-LegacyOnyx {
    $projectsJson = & docker compose ls --format json
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to list existing Docker Compose projects."
    }
    if (-not $projectsJson) {
        return
    }

    $legacyProjects = @($projectsJson | ConvertFrom-Json | Where-Object { $_.Name -eq "onyx" })
    foreach ($legacyProject in $legacyProjects) {
        $composeFiles = @($legacyProject.ConfigFiles -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if ($composeFiles.Count -eq 0) {
            throw "Legacy Onyx project has no recorded Compose files; refusing to stop it."
        }

        Write-Host "Stopping legacy Onyx Compose project 'onyx' without removing volumes."
        # Legacy command shape: docker compose --project-name onyx down
        $composeArguments = @()
        foreach ($composeFile in $composeFiles) {
            $composeArguments += @("-f", $composeFile)
        }
        & docker compose @composeArguments --project-name onyx down
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to stop legacy Onyx Compose project 'onyx'."
        }
    }
}

function Ensure-OnyxEnvironment {
    param([Parameter(Mandatory)][string]$EnvironmentPath)

    if (Test-Path -LiteralPath $EnvironmentPath) {
        return
    }

    $secretBytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
    $secret = [Convert]::ToBase64String($secretBytes)
    $content = "AUTH_TYPE=basic`nUSER_AUTH_SECRET=$secret`n"
    [System.IO.File]::WriteAllText(
        $EnvironmentPath,
        $content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Wait-OnyxHealth {
    param(
        [Parameter(Mandatory)][string]$HealthUrl,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    throw "Onyx API did not become healthy at $HealthUrl within $TimeoutSeconds seconds."
}

Require-Command git
Require-Command docker

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$projectEnvironment = Get-ProjectEnvironment -ProjectRoot $projectRoot
$uiPortValue = if ($env:ONYX_WEB_UI_PORT) {
    $env:ONYX_WEB_UI_PORT
} elseif ($projectEnvironment.ContainsKey("ONYX_WEB_UI_PORT")) {
    $projectEnvironment["ONYX_WEB_UI_PORT"]
} else {
    "3001"
}

[int]$uiPort = 0
if (-not [int]::TryParse($uiPortValue, [ref]$uiPort) -or $uiPort -lt 1 -or $uiPort -gt 65535) {
    throw "ONYX_WEB_UI_PORT must be an integer from 1 through 65535."
}

$onyxRoot = Join-Path $projectRoot ".onyx\onyx"
$composeDir = Join-Path $onyxRoot "deployment\docker_compose"
$overrideSource = Join-Path $projectRoot "infra\onyx\docker-compose.vbpl-ui.yml"
$overrideTarget = Join-Path $composeDir "docker-compose.vbpl-ui.yml"
$environmentPath = Join-Path $composeDir ".env"

if (-not (Test-Path -LiteralPath $onyxRoot)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $onyxRoot) -Force | Out-Null
    & git clone --depth 1 https://github.com/onyx-dot-app/onyx.git $onyxRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to clone the official Onyx repository."
    }
}

if (-not (Test-Path -LiteralPath $composeDir)) {
    throw "Onyx Compose directory was not found at $composeDir."
}
if (-not (Test-Path -LiteralPath $overrideSource)) {
    throw "Tracked Onyx Compose override was not found at $overrideSource."
}

Stop-LegacyOnyx
Ensure-OnyxEnvironment -EnvironmentPath $environmentPath
Copy-Item -LiteralPath $overrideSource -Destination $overrideTarget -Force

Push-Location $composeDir
try {
    & docker compose --project-name vbpl-onyx `
        -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.vbpl-ui.yml `
        --profile s3-filestore up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to start Onyx Compose project 'vbpl-onyx'."
    }
} finally {
    Pop-Location
}

Wait-OnyxHealth -HealthUrl "http://127.0.0.1:8080/health" -TimeoutSeconds $HealthTimeoutSeconds
Write-Host "Onyx is ready at http://127.0.0.1:$uiPort"
