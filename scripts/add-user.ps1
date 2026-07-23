[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Username,

    [string]$Password = "",

    [ValidateSet("BASIC", "ADMIN", "LIMITED")]
    [string]$Role = "BASIC",

    [string]$PersonalName = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Ensure username is formatted / validated
$email = $Username.Trim()
if (-not $email.Contains("@")) {
    $email = "$email@netnam.com"
}

if (-not $Password) {
    $Password = "DemoUser123456!"
}

if (-not $PersonalName) {
    $namePart = ($email.Split("@")[0])
    $PersonalName = (Get-Culture).TextInfo.ToTitleCase($namePart) + " User"
}

$RoleUpper = $Role.ToUpper()

Write-Host "Adding / updating Onyx user '$email' (Role: $RoleUpper)..." -ForegroundColor Cyan

# 1. Verify Docker containers are running
$apiContainer = "vbpl-onyx-api_server-1"
$dbContainer = "vbpl-onyx-relational_db-1"

$runningContainers = docker ps --format "{{.Names}}"
if (-not ($runningContainers -contains $apiContainer) -or -not ($runningContainers -contains $dbContainer)) {
    throw "Onyx containers ($apiContainer, $dbContainer) are not running. Please start Onyx first using `.\scripts\start-onyx.ps1`."
}

# 2. Generate Argon2id password hash using Onyx's FastAPI-Users PasswordHelper
Write-Host "Generating password hash..." -ForegroundColor Gray
$hashCmd = "from fastapi_users.password import PasswordHelper; print(PasswordHelper().hash('''$Password'''))"
$hashedPassword = (docker exec $apiContainer python -c $hashCmd).Trim()

if (-not $hashedPassword -or -not $hashedPassword.StartsWith("$")) {
    throw "Failed to generate password hash from container."
}

# 3. Insert or update user in PostgreSQL database
Write-Host "Saving user record to Onyx database..." -ForegroundColor Gray

$escapedName = $PersonalName.Replace("'", "''")
$escapedEmail = $email.Replace("'", "''")
$escapedHash = $hashedPassword.Replace("'", "''")

$sqlQuery = @"
INSERT INTO "user" (
    id, email, hashed_password, is_active, is_superuser, is_verified, role, account_type, personal_name
) VALUES (
    gen_random_uuid(),
    '$escapedEmail',
    '$escapedHash',
    true,
    $($RoleUpper -eq "ADMIN" | ForEach-Object { if($_){"true"}else{"false"} }),
    true,
    '$RoleUpper',
    'STANDARD',
    '$escapedName'
)
ON CONFLICT (email) DO UPDATE SET
    hashed_password = '$escapedHash',
    role = '$RoleUpper',
    is_active = true,
    is_verified = true,
    is_superuser = $($RoleUpper -eq "ADMIN" | ForEach-Object { if($_){"true"}else{"false"} }),
    personal_name = '$escapedName';
"@

$sqlQuery = $sqlQuery.Replace("`r`n", " ").Replace("`n", " ")
$dbCmd = "docker exec -i $dbContainer psql -U postgres -d postgres"

$res = $sqlQuery | docker exec -i $dbContainer psql -U postgres -d postgres 2>&1

if ($LASTEXITCODE -ne 0) {
    throw "Failed to execute database query: $res"
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " Onyx User Configured Successfully!" -ForegroundColor Green
Write-Host " Email / Username: $email" -ForegroundColor Yellow
Write-Host " Password         : $Password" -ForegroundColor Yellow
Write-Host " Role             : $RoleUpper" -ForegroundColor Yellow
Write-Host " Status           : Active & Verified" -ForegroundColor Gray
Write-Host " Login URL        : http://127.0.0.1:3001" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Green
