<#
.SYNOPSIS
    Start a kubectl port-forward for a Vidya KIND cluster service.

.DESCRIPTION
    Opens a port-forward from localhost to the named service in the cluster.
    Runs in the foreground — press Ctrl+C to stop.

    Port assignments (non-conflicting with docker-compose local stack):
      api          localhost:8080  -> svc/vidya-api:8000
      frontend     localhost:5174  -> svc/vidya-frontend:3000
      flower       localhost:5556  -> svc/vidya-flower:5555
      minio        localhost:9002  -> svc/vidya-minio:9000
      qdrant       localhost:6334  -> svc/vidya-qdrant:6333
      postgres     localhost:5434  -> svc/vidya-postgres:5432
      pgbouncer    localhost:5433  -> svc/vidya-pgbouncer:5432
      redis        localhost:6380  -> svc/vidya-redis:6379
      ingress      localhost:8088  -> svc/ingress-nginx-controller:80 (ns: ingress-nginx)
                   Then open: http://vidya.127.0.0.1.nip.io:8088/

.PARAMETER Service
    Service to forward (required). See list above.

.PARAMETER LocalPort
    Override the default local port.

.PARAMETER Namespace
    Target namespace. Default: vidya-system (ingress uses ingress-nginx).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service api
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service ingress
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service postgres -LocalPort 5450
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service list
#>
param(
    [Parameter(Mandatory)][string]$Service,
    [int]$LocalPort = 0,
    [string]$Namespace = "vidya-system"
)

# Map: service → (local port, svc resource, remote port, namespace override)
$serviceMap = [ordered]@{
    "api"       = @{ local = 8080; svc = "svc/vidya-api";                remote = 8000; ns = "vidya-system";  note = "FastAPI -> http://localhost:8080/docs" }
    "frontend"  = @{ local = 5174; svc = "svc/vidya-frontend";           remote = 3000; ns = "vidya-system";  note = "React UI -> http://localhost:5174" }
    "flower"    = @{ local = 5556; svc = "svc/vidya-flower";             remote = 5555; ns = "vidya-system";  note = "Celery monitor -> http://localhost:5556" }
    "minio"     = @{ local = 9002; svc = "svc/vidya-minio";              remote = 9000; ns = "vidya-system";  note = "MinIO S3 API -> http://localhost:9002" }
    "qdrant"    = @{ local = 6334; svc = "svc/vidya-qdrant";             remote = 6333; ns = "vidya-system";  note = "Qdrant REST -> http://localhost:6334/dashboard" }
    "postgres"  = @{ local = 5434; svc = "svc/vidya-postgres";           remote = 5432; ns = "vidya-system";  note = "Direct Postgres: psql -h localhost -p 5434 -U vidya vidya" }
    "pgbouncer" = @{ local = 5433; svc = "svc/vidya-pgbouncer";          remote = 5432; ns = "vidya-system";  note = "Pooled: psql -h localhost -p 5433 -U vidya vidya" }
    "redis"     = @{ local = 6380; svc = "svc/vidya-redis";              remote = 6379; ns = "vidya-system";  note = "Redis CLI: redis-cli -p 6380" }
    "ingress"   = @{ local = 8088; svc = "svc/ingress-nginx-controller"; remote = 80;   ns = "ingress-nginx"; note = "Full ingress -> http://vidya.127.0.0.1.nip.io:8088/" }
}

# Show all mappings if 'list' requested
if ($Service.ToLower() -eq "list") {
    Write-Host ""
    Write-Host "Available port-forwards (localhost -> cluster):" -ForegroundColor Cyan
    Write-Host ""
    foreach ($k in $serviceMap.Keys) {
        $e = $serviceMap[$k]
        Write-Host ("  {0,-12} localhost:{1} -> {2}:{3}  ({4})" -f $k, $e.local, $e.svc, $e.remote, $e.note) -ForegroundColor White
    }
    Write-Host ""
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service <name>"
    exit 0
}

$entry = $serviceMap[$Service.ToLower()]
if (-not $entry) {
    Write-Host "Unknown service: '$Service'" -ForegroundColor Red
    Write-Host "Run with -Service list to see all options."
    exit 1
}

$effectiveLocal  = if ($LocalPort -gt 0) { $LocalPort } else { $entry.local }
$effectiveNs     = if ($Namespace -ne "vidya-system") { $Namespace } else { $entry.ns }
$svcResource     = $entry.svc
$remotePort      = $entry.remote

Write-Host ""
Write-Host "[kind-port-forward] Forwarding: localhost:${effectiveLocal} -> ${svcResource}:${remotePort}  (ns: $effectiveNs)" -ForegroundColor Cyan
Write-Host "[kind-port-forward] Note: $($entry.note)" -ForegroundColor Cyan
Write-Host "[kind-port-forward] Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

kubectl port-forward $svcResource "${effectiveLocal}:${remotePort}" -n $effectiveNs
