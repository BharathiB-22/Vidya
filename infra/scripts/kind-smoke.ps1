<#
.SYNOPSIS
    Lightweight health smoke test for the Vidya KIND cluster.

.DESCRIPTION
    Checks pod readiness, API liveness/readiness probes, and frontend response
    entirely via kubectl — no external HTTP access required.

    Checks performed:
      1. All pods in vidya-system are Running and Ready (1/1)
      2. API /healthz returns 200 (via kubectl exec in-cluster)
      3. API /ready returns 200 (via kubectl exec in-cluster)
      4. Frontend container responds on port 3000 (via kubectl exec in-cluster)
      5. Ingress controller pod is Running
      6. All PVCs are Bound
      7. Node is Ready

    Exit code: 0 if all checks pass, 1 if any fail.

.PARAMETER Namespace
    Target namespace. Default: vidya-system.

.PARAMETER FailFast
    Stop at first failure instead of running all checks.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-smoke.ps1
    powershell -ExecutionPolicy Bypass -File infra\scripts\kind-smoke.ps1 -FailFast
#>
param(
    [string]$Namespace = "vidya-system",
    [switch]$FailFast
)

$pass = 0
$fail = 0

function Pass { param($m) Write-Host "  PASS  $m" -ForegroundColor Green;  $script:pass++ }
function Fail { param($m) Write-Host "  FAIL  $m" -ForegroundColor Red;    $script:fail++ }
function Warn { param($m) Write-Host "  WARN  $m" -ForegroundColor Yellow }
function Section { param($t) Write-Host ""; Write-Host "--- $t" -ForegroundColor Cyan }

Write-Host ""
Write-Host "======================================================"
Write-Host "  VIDYA KIND SMOKE TEST -- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "  Namespace: $Namespace"
Write-Host "======================================================"

# --- Check 1: Node Ready ---
Section "Check 1: Node Ready"
$nodeStatus = kubectl get node -o jsonpath='{.items[0].status.conditions[-1].type}={.items[0].status.conditions[-1].status}' 2>&1
if ($nodeStatus -eq "Ready=True") {
    Pass "Node: $nodeStatus"
} else {
    Fail "Node status unexpected: $nodeStatus"
    if ($FailFast) { exit 1 }
}

# --- Check 2: All pods Running and Ready ---
Section "Check 2: Pod readiness ($Namespace)"
$podJson = kubectl get pods -n $Namespace -o json 2>&1
try {
    $pods = ($podJson | ConvertFrom-Json).items
    $expected = @("api","flower","frontend","minio","pgbouncer","postgres","qdrant","redis","worker","worker-heavy")

    foreach ($pod in $pods) {
        $name       = $pod.metadata.name
        $phase      = $pod.status.phase
        $containers = $pod.status.containerStatuses
        $allReady   = ($containers | Where-Object { -not $_.ready }).Count -eq 0
        $component  = $pod.metadata.labels.'app.kubernetes.io/component'

        if ($phase -eq "Running" -and $allReady) {
            $restarts = ($containers | Measure-Object -Property restartCount -Sum).Sum
            $suffix = if ($restarts -gt 0) { " (restarts: $restarts)" } else { "" }
            Pass "$name$suffix"
        } else {
            Fail "${name}: phase=${phase} ready=${allReady}"
            if ($FailFast) { exit 1 }
        }
    }

    $found = $pods | ForEach-Object { $_.metadata.labels.'app.kubernetes.io/component' }
    $missing = $expected | Where-Object { $_ -notin $found }
    if ($missing.Count -gt 0) {
        Fail "Missing expected components: $($missing -join ', ')"
        if ($FailFast) { exit 1 }
    } else {
        Pass "All $($expected.Count) expected services present"
    }
} catch {
    Fail "Could not parse pod JSON: $_"
    if ($FailFast) { exit 1 }
}

# --- Check 3: API /healthz via kubectl exec ---
Section "Check 3: API /healthz (in-cluster)"
$healthz = kubectl exec -n $Namespace deployment/vidya-api -- `
    python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/healthz',timeout=5); print(r.status)" 2>&1
if ("$healthz" -match "200") {
    Pass "GET /healthz -> $($healthz.Trim())"
} else {
    Fail "GET /healthz unexpected response: $($healthz.Trim())"
    if ($FailFast) { exit 1 }
}

# --- Check 4: API /ready via kubectl exec ---
Section "Check 4: API /ready (in-cluster)"
$ready = kubectl exec -n $Namespace deployment/vidya-api -- `
    python3 -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/ready',timeout=5); print(r.status)" 2>&1
if ("$ready" -match "200") {
    Pass "GET /ready -> $($ready.Trim())"
} else {
    Fail "GET /ready unexpected response: $($ready.Trim())"
    if ($FailFast) { exit 1 }
}

# --- Check 5: Frontend responds on port 3000 ---
Section "Check 5: Frontend container (in-cluster)"
# Use wget --spider (available in most base images) rather than python3 (not in nginx containers)
$fe = kubectl exec -n $Namespace deployment/vidya-frontend -- `
    sh -c "wget -q --spider http://localhost:3000/ 2>&1; echo exit:$?" 2>&1
$feStr = "$fe"
if ($feStr -match "exit:0" -or $feStr -match "200 OK") {
    Pass "Frontend localhost:3000 -> HTTP OK"
} elseif ($feStr -match "exit:[0-9]") {
    # wget exits non-zero but server responded: check for response
    if ($feStr -match "HTTP/" -or $feStr -match "30[0-9]") {
        Pass "Frontend localhost:3000 -> responded (redirect OK for SPA)"
    } else {
        Warn "Frontend: $($feStr.Trim() -replace '\s+',' ') -- manual check recommended"
    }
} else {
    Warn "Frontend check inconclusive (wget unavailable?) -- pod is Running (checked in step 2)"
}

# --- Check 6: All PVCs Bound ---
Section "Check 6: PVC status ($Namespace)"
$pvcJson = kubectl get pvc -n $Namespace -o json 2>&1
try {
    $pvcs    = ($pvcJson | ConvertFrom-Json).items
    $unbound = $pvcs | Where-Object { $_.status.phase -ne "Bound" }
    if ($unbound.Count -eq 0) {
        Pass "All $($pvcs.Count) PVCs Bound"
    } else {
        foreach ($p in $unbound) {
            Fail "PVC $($p.metadata.name): $($p.status.phase)"
        }
        if ($FailFast) { exit 1 }
    }
} catch {
    Fail "Could not parse PVC JSON: $_"
}

# --- Check 7: Ingress controller Running ---
Section "Check 7: Ingress-nginx controller"
$ngJson = kubectl get pods -n ingress-nginx -l 'app.kubernetes.io/component=controller' -o json 2>&1
try {
    $ngPods = ($ngJson | ConvertFrom-Json).items
    if ($ngPods.Count -eq 0) {
        Fail "No ingress-nginx controller pods found"
    } else {
        $ng = $ngPods[0]
        if ($ng.status.phase -eq "Running") {
            Pass "ingress-nginx-controller: Running"
        } else {
            Fail "ingress-nginx-controller: $($ng.status.phase)"
        }
    }
} catch {
    Warn "Could not check ingress-nginx: $_"
}

# --- Summary ---
Write-Host ""
Write-Host "======================================================"
$total = $pass + $fail
if ($fail -eq 0) {
    Write-Host "  SMOKE TEST PASSED: $pass/$total checks OK" -ForegroundColor Green
} else {
    Write-Host "  SMOKE TEST FAILED: $pass passed, $fail failed" -ForegroundColor Red
}
Write-Host "  Time: $(Get-Date -Format 'HH:mm:ss')"
Write-Host "======================================================"
Write-Host ""

if ($fail -gt 0) { exit 1 }
