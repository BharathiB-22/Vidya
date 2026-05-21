<#
.SYNOPSIS
    Stream or tail logs from a Vidya KIND cluster service.

.DESCRIPTION
    Fetches logs from the named service's deployment or statefulset.
    Use -Follow to tail live. Use -Previous to see logs from a prior container.

    Supported services:
      api  frontend  worker  worker-heavy  flower  pgbouncer
      postgres  redis  minio  qdrant

.PARAMETER Service
    The service to fetch logs from (required).

.PARAMETER Tail
    Number of recent lines to show. Default: 100.

.PARAMETER Follow
    Stream logs live (Ctrl+C to stop).

.PARAMETER Previous
    Show logs from the previous terminated container (useful after a crash).

.PARAMETER Namespace
    Target namespace. Default: vidya-system.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service worker -Follow
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service postgres -Tail 50
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api -Previous
#>
param(
    [Parameter(Mandatory)][string]$Service,
    [int]$Tail = 100,
    [switch]$Follow,
    [switch]$Previous,
    [string]$Namespace = "vidya-system"
)

# Map service name → kubernetes resource reference
$serviceMap = @{
    "api"          = "deployment/vidya-api"
    "frontend"     = "deployment/vidya-frontend"
    "worker"       = "deployment/vidya-worker"
    "worker-heavy" = "deployment/vidya-worker-heavy"
    "flower"       = "deployment/vidya-flower"
    "pgbouncer"    = "deployment/vidya-pgbouncer"
    "postgres"     = "statefulset/vidya-postgres"
    "redis"        = "statefulset/vidya-redis"
    "minio"        = "statefulset/vidya-minio"
    "qdrant"       = "statefulset/vidya-qdrant"
}

$resource = $serviceMap[$Service.ToLower()]
if (-not $resource) {
    Write-Host "Unknown service: '$Service'" -ForegroundColor Red
    Write-Host "Valid services: $($serviceMap.Keys -join ', ')"
    exit 1
}

Write-Host "[kind-logs] $resource  tail=$Tail  follow=$Follow  previous=$Previous  ns=$Namespace" -ForegroundColor Cyan

$args = @("logs", "-n", $Namespace, $resource, "--tail=$Tail")
if ($Follow)   { $args += "-f" }
if ($Previous) { $args += "--previous" }

kubectl @args
