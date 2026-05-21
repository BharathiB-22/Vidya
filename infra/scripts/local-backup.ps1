<#
.SYNOPSIS
    Local docker-compose backup orchestrator for Vidya.

.DESCRIPTION
    Backs up PostgreSQL, MinIO, and Qdrant from the running docker-compose stack
    to a local directory. Safe to run at any time without stopping containers.
    Vault is not in the local compose stack and is explicitly skipped.

.PARAMETER BackupDir
    Directory to store backup files. Default: infra/backups (relative to repo root).

.PARAMETER RetentionDays
    Number of days to keep backup files. Default: 7.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\local-backup.ps1
    powershell -ExecutionPolicy Bypass -File infra\scripts\local-backup.ps1 -BackupDir D:\vidya-backups -RetentionDays 14
#>
param(
    [string]$BackupDir = (Join-Path $PSScriptRoot "..\..\infra\backups"),
    [int]$RetentionDays = 7
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not [System.IO.Path]::IsPathRooted($BackupDir)) {
    $BackupDir = Join-Path (Get-Location).Path $BackupDir
}
$BackupDir = [System.IO.Path]::GetFullPath($BackupDir)
$Timestamp = (Get-Date -Format "yyyyMMdd_HHmmssZ")
$LogPrefix = "[local-backup]"
$StartTime = Get-Date

function Log  { param($m) Write-Host "$LogPrefix $(Get-Date -Format 'HH:mm:ss')Z $m" }
function Warn { param($m) Write-Host "$LogPrefix WARN: $m" -ForegroundColor Yellow }
function Fail { param($m) Write-Host "$LogPrefix FAIL: $m" -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Log "Backup directory: $BackupDir"
Log "Timestamp: $Timestamp"
Log "Retention: $RetentionDays days"
Log ""

$manifest = [ordered]@{
    timestamp  = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    host       = $env:COMPUTERNAME
    components = [ordered]@{}
}

# --- Step 1: PostgreSQL ---
Log "=== Step 1: PostgreSQL dump ==="
$dumpFile   = Join-Path $BackupDir "vidya_postgres_${Timestamp}.dump"
$sha256File = "${dumpFile}.sha256"

try {
    # Create dump inside container to avoid binary pipe corruption on Windows
    docker exec vidya-postgres-1 pg_dump -U vidya vidya --format=custom -f /tmp/backup.dump
    if ($LASTEXITCODE -ne 0) { Fail "pg_dump failed (exit $LASTEXITCODE)" }

    $sizeStr = docker exec vidya-postgres-1 stat -c "%s" /tmp/backup.dump
    if ([int]$sizeStr -eq 0) { Fail "pg_dump output is empty" }
    Log "Dump inside container: $sizeStr bytes"

    docker cp "vidya-postgres-1:/tmp/backup.dump" $dumpFile
    if ($LASTEXITCODE -ne 0) { Fail "docker cp failed" }

    docker exec vidya-postgres-1 rm /tmp/backup.dump
    $dumpSize = (Get-Item $dumpFile).Length
    $pgHash = (Get-FileHash -Path $dumpFile -Algorithm SHA256).Hash.ToLower()
    "$pgHash  vidya_postgres_${Timestamp}.dump" | Set-Content -Path $sha256File -Encoding utf8

    Log "PostgreSQL DONE -- size=$dumpSize bytes sha256=$pgHash"
    $manifest.components.postgres = [ordered]@{
        file       = "vidya_postgres_${Timestamp}.dump"
        size_bytes = $dumpSize
        sha256     = $pgHash
        status     = "success"
    }
} catch {
    Warn "PostgreSQL backup failed: $_"
    $manifest.components.postgres = @{ status = "failure"; error = "$_" }
}

# --- Step 2: MinIO volume-level backup ---
Log ""
Log "=== Step 2: MinIO volume backup ==="
$minioFile = Join-Path $BackupDir "vidya_minio_${Timestamp}.tar.gz"

try {
    $backupDirForDocker = $BackupDir.Replace('\', '/')
    $tarName = "vidya_minio_${Timestamp}.tar.gz"
    docker run --rm `
        -v "vidya_minio_data:/data:ro" `
        -v "${backupDirForDocker}:/backup" `
        alpine sh -c "tar czf /backup/$tarName -C /data . && echo TAR_OK"

    if ($LASTEXITCODE -ne 0) { throw "docker run alpine tar failed (exit $LASTEXITCODE)" }

    $minioItem = Get-Item $minioFile -ErrorAction SilentlyContinue
    if ($null -eq $minioItem -or $minioItem.Length -eq 0) { throw "MinIO tar file is empty or missing" }
    $minioSize = $minioItem.Length
    $minioHash = (Get-FileHash -Path $minioFile -Algorithm SHA256).Hash.ToLower()
    "$minioHash  ${tarName}" | Set-Content -Path "${minioFile}.sha256" -Encoding utf8

    Log "MinIO DONE -- size=$minioSize bytes sha256=$minioHash"
    $manifest.components.minio = [ordered]@{
        file       = $tarName
        size_bytes = $minioSize
        sha256     = $minioHash
        status     = "success"
        note       = "Volume-level backup of vidya_minio_data"
    }
} catch {
    Warn "MinIO backup failed: $_"
    $manifest.components.minio = @{ status = "failure"; error = "$_" }
}

# --- Step 3: Qdrant REST snapshot per collection ---
Log ""
Log "=== Step 3: Qdrant snapshot backup ==="

try {
    $resp        = Invoke-RestMethod -Uri "http://localhost:6333/collections" -ErrorAction Stop
    $collections = $resp.result.collections

    if ($collections.Count -eq 0) {
        Log "Qdrant: no collections -- skipping (expected on fresh install)"
        $manifest.components.qdrant = @{ status = "skipped"; note = "No collections" }
    } else {
        $qdrantResults = @()
        foreach ($coll in $collections) {
            $collName = $coll.name
            Log "  Snapshot for collection: $collName"

            $snapResp = Invoke-RestMethod -Method Post -Uri "http://localhost:6333/collections/$collName/snapshots"
            $snapName = $snapResp.result.name
            $snapFileName = "vidya_qdrant_${collName}_${Timestamp}.snapshot"
            $snapFile = Join-Path $BackupDir $snapFileName

            Invoke-WebRequest -Uri "http://localhost:6333/collections/$collName/snapshots/$snapName" -OutFile $snapFile
            $snapSize = (Get-Item $snapFile).Length
            $snapHash = (Get-FileHash -Path $snapFile -Algorithm SHA256).Hash.ToLower()
            "$snapHash  $snapFileName" | Set-Content "${snapFile}.sha256" -Encoding utf8

            Invoke-RestMethod -Method Delete -Uri "http://localhost:6333/collections/$collName/snapshots/$snapName" | Out-Null

            Log "  ${collName} DONE -- size=$snapSize bytes sha256=$snapHash"
            $qdrantResults += [ordered]@{
                collection = $collName
                file       = $snapFileName
                size_bytes = $snapSize
                sha256     = $snapHash
            }
        }
        $manifest.components.qdrant = [ordered]@{ status = "success"; snapshots = $qdrantResults }
    }
} catch {
    Warn "Qdrant backup failed or Qdrant not reachable: $_"
    $manifest.components.qdrant = @{ status = "failure"; error = "$_" }
}

# --- Step 4: Vault (skip — not in local docker-compose) ---
Log ""
Log "=== Step 4: Vault ==="
Log "Vault is not in local docker-compose -- skipping."
Log "For production: bash infra/scripts/backup-vault.sh"
$manifest.components.vault = @{ status = "skipped"; note = "Vault not in local docker-compose" }

# --- Write manifest ---
Log ""
Log "=== Writing manifest ==="
$manifest.duration_seconds = [int](New-TimeSpan -Start $StartTime -End (Get-Date)).TotalSeconds
$manifestPath = Join-Path $BackupDir "manifest_${Timestamp}.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding utf8
Log "Manifest: $manifestPath"

# --- Prune old backups ---
Log ""
Log "=== Pruning backups older than $RetentionDays days ==="
$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $BackupDir -File | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
    Log "  Removing: $($_.Name)"
    Remove-Item $_.FullName -Force
}

# --- Summary ---
Log ""
Log "=== Backup complete ==="
$totalDuration = [int](New-TimeSpan -Start $StartTime -End (Get-Date)).TotalSeconds
Log "Duration: ${totalDuration}s"
Log "Files in backup dir:"
Get-ChildItem $BackupDir -File | Sort-Object LastWriteTime -Descending | ForEach-Object {
    $kb = [math]::Round($_.Length / 1KB, 1)
    Log "  $($_.Name) (${kb} KB)"
}
