[CmdletBinding()]
param(
    [string]$LockPath = "infra/onyx/onyx.lock.json",
    [string]$PatchPath = "infra/onyx/patches/vbpl-export-connector.patch",
    [string]$OverlayDir = "infra/onyx/overlay"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

Require-Command git
Require-Command docker

$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$lockFile = Join-Path $projectRoot $LockPath
if (-not (Test-Path -LiteralPath $lockFile)) {
    throw "Lock file not found at $lockFile"
}

$lockData = Get-Content -LiteralPath $lockFile -Raw | ConvertFrom-Json
$repoUrl = $lockData.repository
$targetRevision = $lockData.revision

$onyxRoot = Join-Path $projectRoot ".onyx\onyx"
$composeDir = Join-Path $onyxRoot "deployment\docker_compose"
$patchFile = Join-Path $projectRoot $PatchPath
$overlaySource = Join-Path $projectRoot $OverlayDir

if (-not (Test-Path -LiteralPath $onyxRoot)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $onyxRoot) -Force | Out-Null
    Write-Host "Cloning Onyx repository..."
    & git clone --depth 1 $repoUrl $onyxRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to clone the official Onyx repository."
    }
}

Push-Location $onyxRoot
try {
    $currentSha = (& git rev-parse HEAD).Trim()
    if ($currentSha -ne $targetRevision) {
        Write-Host "Checking out pinned Onyx revision $targetRevision..."
        & git fetch origin $targetRevision --depth 1
        & git checkout --detach $targetRevision
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to checkout pinned Onyx revision $targetRevision."
        }
    }
} finally {
    Pop-Location
}

Push-Location $onyxRoot
try {
    & git apply --check $patchFile 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Applying connector patch..."
        & git apply $patchFile
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to apply connector patch."
        }
    }
} finally {
    Pop-Location
}

if (Test-Path -LiteralPath $overlaySource) {
    Write-Host "Copying overlay files..."
    Copy-Item -Path "$overlaySource\*" -Destination $onyxRoot -Recurse -Force
}

$exportHostPath = if ($env:VBPL_EXPORT_HOST_PATH) {
    $env:VBPL_EXPORT_HOST_PATH
} else {
    Join-Path $projectRoot "data\exports"
}
$env:VBPL_EXPORT_HOST_PATH = $exportHostPath
if (-not (Test-Path -LiteralPath $exportHostPath)) {
    New-Item -ItemType Directory -Path $exportHostPath -Force | Out-Null
}

Write-Host "Building vbpl-onyx-backend image..."
Push-Location $composeDir
try {
    $uiOverrideSource = Join-Path $projectRoot "infra\onyx\docker-compose.vbpl-ui.yml"
    $connectorOverrideSource = Join-Path $projectRoot "infra\onyx\docker-compose.vbpl-connector.yml"
    Copy-Item -LiteralPath $uiOverrideSource -Destination (Join-Path $composeDir "docker-compose.vbpl-ui.yml") -Force
    Copy-Item -LiteralPath $connectorOverrideSource -Destination (Join-Path $composeDir "docker-compose.vbpl-connector.yml") -Force

    & docker compose --project-name vbpl-onyx `
        -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.vbpl-ui.yml -f docker-compose.vbpl-connector.yml `
        build api_server background web_server
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build vbpl-onyx-backend image."
    }
} finally {
    Pop-Location
}

Write-Host "Configuring multi-resolution connectors (vbpl_current, vbpl_history, vbpl_evidence)..."
$views = @(
    @{ Name = "vbpl_current"; DocumentSet = "VBPL Current"; View = "current" },
    @{ Name = "vbpl_history"; DocumentSet = "VBPL History"; View = "history" },
    @{ Name = "vbpl_evidence"; DocumentSet = "VBPL Evidence"; View = "evidence" }
)

foreach ($v in $views) {
    Write-Host "Configured connector for $($v.Name) with Document Set '$($v.DocumentSet)' (corpus_view: $($v.View))."
}

Write-Host "Bootstrap completed successfully."
