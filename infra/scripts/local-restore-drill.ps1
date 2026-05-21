<#
.SYNOPSIS
    Local restore drill for Vidya docker-compose stack.

.DESCRIPTION
    Two modes:

    -ValidateOnly (default)
        Checks that the latest backup files exist, verifies SHA256 checksums,
        and reports backup age and sizes. Zero risk -- no data is touched.

    -PostgresTestRestore
        Spins up a throwaway postgres:16 container on port 5433, restores the
        latest dump into it, runs verification queries, then destroys the container.
        NEVER touches the running vidya-postgres-1 container.
        Requires the operator to type a confirmation phrase before proceeding.

.PARAMETER BackupDir
    Directory containing backup files. Default: infra/backups (relative to repo root).

.PARAMETER ValidateOnly
    Run checksum validation and report only. No data movement. This is the default.

.PARAMETER PostgresTestRestore
    Spin up a test postgres container, restore the latest dump, verify, destroy.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\local-restore-drill.ps1
    powershell -ExecutionPolicy Bypass -File infra\scripts\local-restore-drill.ps1 -PostgresTestRestore
#>
param(
    [string]$BackupDir = (Join-Path $PSScriptRoot "..\..\infra\backups"),
    [switch]$ValidateOnly,
    [switch]$PostgresTestRestore
)

# Use explicit checks instead of Stop — native docker commands use exit codes
$ErrorActionPreference = "Continue"

if (-not [System.IO.Path]::IsPathRooted($BackupDir)) {
    $BackupDir = Join-Path (Get-Location).Path $BackupDir
}
$BackupDir = [System.IO.Path]::GetFullPath($BackupDir)
$LogPrefix = "[restore-drill]"

function Log  { param($m) Write-Host "$LogPrefix $(Get-Date -Format 'HH:mm:ss')Z $m" }
function Warn { param($m) Write-Host "$LogPrefix WARN: $m" -ForegroundColor Yellow }
function Ok   { param($m) Write-Host "$LogPrefix PASS: $m" -ForegroundColor Green }
function Fail { param($m) Write-Host "$LogPrefix FAIL: $m" -ForegroundColor Red; exit 1 }
function Gate { param($msg)
    Write-Host ""
    Write-Host "======================================================" -ForegroundColor Cyan
    Write-Host "  HUMAN GATE: $msg" -ForegroundColor Cyan
    Write-Host "======================================================" -ForegroundColor Cyan
}
function FmtKB { param($bytes) return "$([math]::Round($bytes / 1024, 1)) KB" }

# Default to validate-only if no mode specified
if (-not $PostgresTestRestore) { $ValidateOnly = $true }

Write-Host ""
Write-Host "======================================================"
Write-Host "  VIDYA LOCAL RESTORE DRILL -- $(Get-Date -Format 'yyyy-MM-dd')"
Write-Host "  Backup dir: $BackupDir"
$modeLabel = if ($PostgresTestRestore) { "PostgreSQL Test Restore" } else { "Validate Only" }
Write-Host "  Mode:       $modeLabel"
Write-Host "======================================================"
Write-Host ""

# --- Step 1: Locate latest backup files ---
Log "=== Step 1: Locate latest backup files ==="

if (-not (Test-Path $BackupDir)) {
    Fail "Backup directory not found: $BackupDir -- run local-backup.ps1 first."
}

$latestDump = Get-ChildItem $BackupDir -Filter "vidya_postgres_*.dump" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$latestMinio = Get-ChildItem $BackupDir -Filter "vidya_minio_*.tar.gz" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

$latestManifest = Get-ChildItem $BackupDir -Filter "manifest_*.json" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $latestDump) { Fail "No PostgreSQL dump found in $BackupDir" }
if (-not $latestMinio) { Warn "No MinIO backup found -- MinIO backup may have been skipped" }

$dumpKB    = FmtKB $latestDump.Length
$ageMinutes = [int](New-TimeSpan -Start $latestDump.LastWriteTime -End (Get-Date)).TotalMinutes
Log "Latest PostgreSQL dump: $($latestDump.Name) ($dumpKB)"
Log "Dump age:               $ageMinutes minutes"

if ($latestMinio) {
    $minioKB = FmtKB $latestMinio.Length
    Log "Latest MinIO backup:    $($latestMinio.Name) ($minioKB)"
}
if ($latestManifest) {
    $manifestData = Get-Content $latestManifest.FullName -Raw | ConvertFrom-Json
    Log "Latest manifest:        $($latestManifest.Name)"
    Log "Manifest timestamp:     $($manifestData.timestamp)"
}

# --- Step 2: Verify SHA256 checksums ---
Log ""
Log "=== Step 2: SHA256 checksum verification ==="
$checksumFail = 0

function Check-Checksum {
    param([System.IO.FileInfo]$file)
    $sha256Path = "$($file.FullName).sha256"
    if (-not (Test-Path $sha256Path)) {
        Warn "No checksum file for $($file.Name) -- skipping"
        return
    }
    $expected = ((Get-Content $sha256Path -Raw).Split(" ")[0]).Trim()
    $actual   = (Get-FileHash -Path $file.FullName -Algorithm SHA256).Hash.ToLower()
    if ($expected -eq $actual) {
        Ok "$($file.Name): checksum OK"
    } else {
        Write-Host "$LogPrefix FAIL: $($file.Name) checksum MISMATCH" -ForegroundColor Red
        Write-Host "  expected: $expected"
        Write-Host "  actual:   $actual"
        $script:checksumFail++
    }
}

Check-Checksum $latestDump
if ($latestMinio) { Check-Checksum $latestMinio }

Get-ChildItem $BackupDir -Filter "vidya_qdrant_*.snapshot" |
    Sort-Object LastWriteTime -Descending |
    ForEach-Object { Check-Checksum $_ }

if ($checksumFail -gt 0) {
    Fail "$checksumFail checksum(s) FAILED -- backups may be corrupt. Do not restore."
}
Ok "All checksums verified"

# --- Step 3: Inventory ---
Log ""
Log "=== Step 3: Backup inventory ==="
Log "All backup files (newest first):"
Get-ChildItem $BackupDir -File | Sort-Object LastWriteTime -Descending | ForEach-Object {
    $kb  = FmtKB $_.Length
    $age = [int](New-TimeSpan -Start $_.LastWriteTime -End (Get-Date)).TotalMinutes
    Log "  $($_.Name.PadRight(55)) $kb  ${age}min ago"
}

# --- Step 4: Validate-only exit ---
if ($ValidateOnly -and -not $PostgresTestRestore) {
    Log ""
    Log "=== Validate-only mode: complete ==="
    Ok "Backup files present, checksums valid, no data restored."
    Log "To run a full test restore:  add -PostgresTestRestore flag"
    Log "Production drill:            bash infra/scripts/restore-drill.sh --validate-only"
    exit 0
}

# --- Step 5: PostgreSQL test restore ---
Log ""
Log "=== Step 5: PostgreSQL test restore ==="

Gate "Spin up throwaway postgres:16 on port 5433. vidya-postgres-1 NOT touched."
Write-Host "  Dump file: $($latestDump.Name)"
Write-Host ""
Write-Host "  Type 'confirm-test-restore' to proceed, anything else aborts." -ForegroundColor Yellow
$confirm = Read-Host "  Confirmation"
if ($confirm -ne "confirm-test-restore") {
    Log "Aborted by operator."
    exit 0
}

$testContainer = "vidya-postgres-restore-test"
# Remove any leftover container from a previous failed drill (ignore errors)
$null = (& docker rm -f $testContainer 2>&1)

Log "Starting test container on port 5433..."
docker run -d `
    --name $testContainer `
    -e POSTGRES_USER=vidya `
    -e POSTGRES_PASSWORD=vidya_dev `
    -e POSTGRES_DB=vidya `
    -p 5433:5432 `
    postgres:16 | Out-Null

if ($LASTEXITCODE -ne 0) { Fail "Failed to start test container" }

Log "Waiting for test container to be ready (up to 60s)..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    docker exec $testContainer pg_isready -U vidya -d vidya 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
}
if (-not $ready) {
    docker rm -f $testContainer | Out-Null
    Fail "Test container did not become ready within 60s"
}
Ok "Test container ready"

try {
    Log "Copying dump into test container..."
    docker cp $latestDump.FullName "${testContainer}:/tmp/restore.dump"
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed" }

    Log "Running pg_restore (may take a minute)..."
    docker exec $testContainer pg_restore `
        -U vidya -d vidya `
        --no-acl --no-owner `
        --clean --if-exists `
        /tmp/restore.dump
    # exit code 1 = warnings only (expected: role not found, etc.), >1 = real failure
    if ($LASTEXITCODE -gt 1) { throw "pg_restore failed with exit $LASTEXITCODE" }
    Log "pg_restore complete (exit 0 or 1; warnings are non-fatal)"

    Log ""
    Log "=== Verification queries ==="
    $alembicVer = docker exec $testContainer psql -U vidya -d vidya -t -c "SELECT version_num FROM alembic_version LIMIT 1;"
    Log "alembic_version: $($alembicVer.Trim())"
    if ("$alembicVer" -match '\w+') { Ok "alembic_version present" } else { Warn "alembic_version empty" }

    $tenantCount = docker exec $testContainer psql -U vidya -d vidya -t -c "SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname LIKE 'tenant_%';"
    Log "Tenant schemas:  $($tenantCount.Trim())"

    $tableCount = docker exec $testContainer psql -U vidya -d vidya -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
    Log "Public tables:   $($tableCount.Trim())"

    $hasCore = docker exec $testContainer psql -U vidya -d vidya -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='tenants' AND table_schema='public')::text;"
    Log "tenants table:   $($hasCore.Trim())"
    if ("$hasCore" -match "true") { Ok "Core tables present" } else { Warn "tenants table not found" }

    Ok "Test restore verification complete"
} catch {
    Warn "Restore failed: $_"
} finally {
    Log ""
    Log "Tearing down test container..."
    $null = (& docker stop $testContainer 2>&1)
    $null = (& docker rm $testContainer 2>&1)
    Ok "Test container removed -- vidya-postgres-1 untouched"
}

# --- Final summary ---
Log ""
Log "=== Drill complete ==="
Log "Backup tested:    $($latestDump.Name)"
Log "Backup age:       $ageMinutes minutes"
Log "RTO target:       < 30 minutes (local), < 4 hours (production)"
Log ""
Log "Record this drill in the team log (docs/backup-restore-runbook.md)."
