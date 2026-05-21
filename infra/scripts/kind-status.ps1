<#
.SYNOPSIS
    Show full operational status of the Vidya KIND cluster.

.DESCRIPTION
    Displays pods, deployments, statefulsets, services, ingress, PVCs,
    and recent warning events in the vidya-system namespace.
    Read-only — no cluster state is modified.

.PARAMETER Namespace
    Target namespace. Default: vidya-system.

.PARAMETER Wide
    Show extra columns (node, IP) in pod listing.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-status.ps1
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-status.ps1 -Wide
#>
param(
    [string]$Namespace = "vidya-system",
    [switch]$Wide
)

$LogPrefix = "[kind-status]"
function Section { param($t) Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok      { param($m) Write-Host "  OK  $m" -ForegroundColor Green }
function Warn    { param($m) Write-Host "  WARN $m" -ForegroundColor Yellow }
function Fail    { param($m) Write-Host "  FAIL $m" -ForegroundColor Red }

Write-Host ""
Write-Host "======================================================"
Write-Host "  VIDYA KIND STATUS -- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "  Namespace: $Namespace"
Write-Host "======================================================"

# --- Cluster node health ---
Section "Cluster Node"
kubectl get nodes -o wide 2>&1

# --- Pods ---
Section "Pods ($Namespace)"
if ($Wide) {
    kubectl get pods -n $Namespace -o wide 2>&1
} else {
    kubectl get pods -n $Namespace 2>&1
}

# Quick ready/not-ready summary
$podJson = kubectl get pods -n $Namespace -o json 2>&1
try {
    $pods = ($podJson | ConvertFrom-Json).items
    $total   = $pods.Count
    $running = ($pods | Where-Object { $_.status.phase -eq "Running" }).Count
    $notReady = $pods | Where-Object {
        $_.status.containerStatuses | Where-Object { -not $_.ready }
    }
    Write-Host ""
    if ($notReady.Count -eq 0) {
        Ok "$running/$total pods Ready"
    } else {
        Fail "$running/$total pods Ready -- not-ready: $($notReady.metadata.name -join ', ')"
    }
} catch {}

# --- Deployments / StatefulSets ---
Section "Deployments and StatefulSets ($Namespace)"
kubectl get deployment,statefulset -n $Namespace 2>&1

# --- Services ---
Section "Services ($Namespace)"
kubectl get svc -n $Namespace 2>&1

# --- Ingress ---
Section "Ingress ($Namespace)"
kubectl get ingress -n $Namespace 2>&1

# --- PVCs ---
Section "Persistent Volume Claims ($Namespace)"
kubectl get pvc -n $Namespace 2>&1

# Quick PVC bound check
$pvcJson = kubectl get pvc -n $Namespace -o json 2>&1
try {
    $pvcs  = ($pvcJson | ConvertFrom-Json).items
    $unbound = $pvcs | Where-Object { $_.status.phase -ne "Bound" }
    if ($unbound.Count -eq 0) {
        Write-Host ""
        Ok "All $($pvcs.Count) PVCs Bound"
    } else {
        Write-Host ""
        Fail "Unbound PVCs: $($unbound.metadata.name -join ', ')"
    }
} catch {}

# --- Jobs ---
Section "Jobs ($Namespace)"
$jobs = kubectl get jobs -n $Namespace 2>&1
if ($jobs -match "No resources") { Write-Host "  (none)" } else { Write-Host $jobs }

# --- Recent Warning events ---
Section "Recent Warning Events ($Namespace, last 20)"
$events = kubectl get events -n $Namespace --sort-by='.lastTimestamp' --field-selector=type=Warning 2>&1
if ($events -match "No resources") {
    Ok "No Warning events"
} else {
    Write-Host $events
}

# --- Ingress controller ---
Section "Ingress-Nginx Controller"
kubectl get pods -n ingress-nginx 2>&1
$nginxSvc = kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.ports[?(@.port==80)].nodePort}' 2>&1
$nodeIp   = kubectl get node vidya-control-plane -o jsonpath="{.status.addresses[0].address}" 2>&1
Write-Host ""
Write-Host "  NodePort HTTP:  $nginxSvc"
Write-Host "  Node IP:        $nodeIp"
Write-Host "  Ingress URL:    http://vidya.127.0.0.1.nip.io (via port-forward or nodeport)"
Write-Host "  Port-forward:   kubectl port-forward svc/ingress-nginx-controller -n ingress-nginx 8088:80"

Write-Host ""
Write-Host "======================================================"
Write-Host "  Status check complete: $(Get-Date -Format 'HH:mm:ss')"
Write-Host "======================================================"
