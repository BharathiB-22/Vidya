<#
.SYNOPSIS
    Perform a rolling restart of a Vidya KIND cluster service.

.DESCRIPTION
    Triggers a kubectl rollout restart for the named service, waits for
    the rollout to complete, and shows the final pod state.

    DESTRUCTIVE: causes a brief pod interruption. Requires typed confirmation.
    Use only for stuck pods or after config changes.

    Supported services:
      api  frontend  worker  worker-heavy  flower  pgbouncer
      postgres  redis  minio  qdrant

.PARAMETER Service
    The service to restart (required).

.PARAMETER Namespace
    Target namespace. Default: vidya-system.

.PARAMETER TimeoutSeconds
    Seconds to wait for rollout completion. Default: 120.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-restart.ps1 -Service api
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-restart.ps1 -Service worker -TimeoutSeconds 180
#>
param(
    [Parameter(Mandatory)][string]$Service,
    [string]$Namespace = "vidya-system",
    [int]$TimeoutSeconds = 120
)

$LogPrefix = "[kind-restart]"
function Log  { param($m) Write-Host "$LogPrefix $(Get-Date -Format 'HH:mm:ss')Z $m" }
function Ok   { param($m) Write-Host "$LogPrefix PASS: $m" -ForegroundColor Green }
function Fail { param($m) Write-Host "$LogPrefix FAIL: $m" -ForegroundColor Red; exit 1 }

# Map service name → kubernetes resource reference and kind
$serviceMap = @{
    "api"          = @{ resource = "deployment/vidya-api";            kind = "deployment" }
    "frontend"     = @{ resource = "deployment/vidya-frontend";       kind = "deployment" }
    "worker"       = @{ resource = "deployment/vidya-worker";         kind = "deployment" }
    "worker-heavy" = @{ resource = "deployment/vidya-worker-heavy";   kind = "deployment" }
    "flower"       = @{ resource = "deployment/vidya-flower";         kind = "deployment" }
    "pgbouncer"    = @{ resource = "deployment/vidya-pgbouncer";      kind = "deployment" }
    "postgres"     = @{ resource = "statefulset/vidya-postgres";      kind = "statefulset" }
    "redis"        = @{ resource = "statefulset/vidya-redis";         kind = "statefulset" }
    "minio"        = @{ resource = "statefulset/vidya-minio";         kind = "statefulset" }
    "qdrant"       = @{ resource = "statefulset/vidya-qdrant";        kind = "statefulset" }
}

$entry = $serviceMap[$Service.ToLower()]
if (-not $entry) {
    Write-Host "Unknown service: '$Service'" -ForegroundColor Red
    Write-Host "Valid services: $($serviceMap.Keys -join ', ')"
    exit 1
}

$resource = $entry.resource

# Show current state before restart
Log "Current pod state for $resource:"
kubectl get pods -n $Namespace -l "app.kubernetes.io/component=$($Service.ToLower())" 2>&1

Write-Host ""
Write-Host "======================================================" -ForegroundColor Yellow
Write-Host "  RESTART: $resource" -ForegroundColor Yellow
Write-Host "  Namespace: $Namespace" -ForegroundColor Yellow
Write-Host "  This triggers a rolling pod replacement." -ForegroundColor Yellow
Write-Host "======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Type 'confirm-restart' to proceed, anything else aborts." -ForegroundColor Yellow
$confirm = Read-Host "  Confirmation"
if ($confirm -ne "confirm-restart") {
    Log "Aborted by operator."
    exit 0
}

Log "Triggering rollout restart: $resource"
kubectl rollout restart $resource -n $Namespace 2>&1
if ($LASTEXITCODE -ne 0) { Fail "rollout restart command failed" }

Log "Waiting for rollout to complete (timeout: ${TimeoutSeconds}s)..."
kubectl rollout status $resource -n $Namespace --timeout="${TimeoutSeconds}s" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "$LogPrefix WARN: rollout did not complete within ${TimeoutSeconds}s" -ForegroundColor Yellow
    Write-Host "$LogPrefix Run: kubectl rollout status $resource -n $Namespace  to check progress" -ForegroundColor Yellow
} else {
    Ok "Rollout complete"
}

Log "Final pod state:"
kubectl get pods -n $Namespace -l "app.kubernetes.io/component=$($Service.ToLower())" 2>&1

# Rollback note
Write-Host ""
Write-Host "  Rollback if needed: kubectl rollout undo $resource -n $Namespace" -ForegroundColor Cyan
