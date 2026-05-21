# KIND Operations Guide — Vidya

**Owner:** Srinivas / Fidelitus Corp  
**Last updated:** 2026-05-21  
**Cluster:** `vidya-control-plane` (KIND v1.35.0, single-node)  
**Namespace:** `vidya-system`

---

## Quick Reference

| Script | Purpose | Safe? |
|--------|---------|-------|
| `kind-status.ps1` | Full cluster snapshot (pods, svc, ingress, PVC, events) | Read-only |
| `kind-logs.ps1 -Service <name>` | Tail logs from any service | Read-only |
| `kind-smoke.ps1` | Health smoke test (all checks in-cluster) | Read-only |
| `kind-port-forward.ps1 -Service <name>` | Local port-forward to a cluster service | Read-only |
| `kind-restart.ps1 -Service <name>` | Rolling restart (requires confirmation) | **Destructive** |

All scripts are in `infra/scripts/`. Run from the repo root.

---

## 1. kind-status.ps1 — Cluster Snapshot

Shows pods, deployments/statefulsets, services, ingress, PVCs, and warning events.

```powershell
# Standard view
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-status.ps1

# Wide view (includes node IP, more columns)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-status.ps1 -Wide
```

**Expected healthy output:**
```
=== Pods (vidya-system) ===
NAME                                 READY   STATUS    RESTARTS   AGE
vidya-api-f867db4bc-wxwcx            1/1     Running   4          29h
vidya-flower-f5995b844-rrm2f         1/1     Running   5          43h
vidya-frontend-5c56fdc96-qptkz       1/1     Running   5          43h
vidya-minio-0                        1/1     Running   5          43h
vidya-pgbouncer-74769c9785-bl7w6     1/1     Running   5          43h
vidya-postgres-0                     1/1     Running   5          43h
vidya-qdrant-0                       1/1     Running   5          43h
vidya-redis-0                        1/1     Running   5          43h
vidya-worker-684bd695dd-vx4m9        1/1     Running   4          38h
vidya-worker-heavy-769694c59-zw82r   1/1     Running   4          38h

  OK  10/10 pods Ready

=== Recent Warning Events (vidya-system) ===
  OK  No Warning events
```

**Troubleshooting signals:**
- Pod in `CrashLoopBackOff` → check logs: `kind-logs.ps1 -Service <name> -Previous`
- Pod in `Pending` → check PVC binding or resource pressure: `kubectl describe pod <name> -n vidya-system`
- PVC `Unbound` → check `kubectl describe pvc <name> -n vidya-system`
- Warning events → investigate before doing anything

---

## 2. kind-logs.ps1 — Service Logs

Supported services: `api`, `frontend`, `worker`, `worker-heavy`, `flower`, `pgbouncer`, `postgres`, `redis`, `minio`, `qdrant`

```powershell
# Last 100 lines (default)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api

# Follow live
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service worker -Follow

# Last 50 lines
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service postgres -Tail 50

# Previous container (after a crash)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api -Previous
```

**Useful log investigation patterns:**

```powershell
# Find ERROR-level entries from api
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api -Tail 500 | Select-String '"level":"ERROR"'

# Find a specific request_id
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api -Tail 1000 | Select-String "abc123"

# Watch worker-heavy for task failures
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service worker-heavy -Follow | Select-String -Pattern "FAILURE|ERROR|exception" -SimpleMatch
```

---

## 3. kind-smoke.ps1 — Health Smoke Test

Runs 7 checks entirely via kubectl — no external network access required:
1. Node Ready
2. All 10 pods Running 1/1 in vidya-system
3. API `/healthz` returns 200 (in-cluster)
4. API `/ready` returns 200 (in-cluster)
5. Frontend container responds on port 3000
6. All PVCs Bound
7. Ingress-nginx controller Running

```powershell
# Full smoke test
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-smoke.ps1

# Stop at first failure
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-smoke.ps1 -FailFast
```

**Expected output (healthy cluster):**
```
=== Check 1: Node Ready ===
  PASS  Node: Ready=True

=== Check 2: Pod readiness (vidya-system) ===
  PASS  vidya-api-... (restarts: 4)
  PASS  vidya-worker-... (restarts: 4)
  ...
  PASS  All 10 expected services present

=== Check 3: API /healthz (in-cluster) ===
  PASS  GET /healthz -> 200

=== Check 4: API /ready (in-cluster) ===
  PASS  GET /ready -> 200

=== Check 5: Frontend container (in-cluster) ===
  PASS  Frontend localhost:3000 -> 200

=== Check 6: PVC status (vidya-system) ===
  PASS  All 4 PVCs Bound

=== Check 7: Ingress-nginx controller ===
  PASS  ingress-nginx-controller: Running

======================================================
  SMOKE TEST PASSED: 13/13 checks OK
======================================================
```

**Exit codes:** 0 = all pass, 1 = any failure. CI-safe.

---

## 4. kind-port-forward.ps1 — Port Forwarding

Opens a local port-forward to a cluster service. Runs in the foreground — Ctrl+C to stop.

Port assignments avoid conflicts with the docker-compose local stack:

| Service | Local port | Cluster target | Access URL |
|---------|-----------|----------------|------------|
| `api` | 8080 | svc/vidya-api:8000 | http://localhost:8080/docs |
| `frontend` | 5174 | svc/vidya-frontend:3000 | http://localhost:5174 |
| `flower` | 5556 | svc/vidya-flower:5555 | http://localhost:5556 |
| `minio` | 9002 | svc/vidya-minio:9000 | http://localhost:9002 |
| `qdrant` | 6334 | svc/vidya-qdrant:6333 | http://localhost:6334/dashboard |
| `postgres` | 5434 | svc/vidya-postgres:5432 | psql -p 5434 |
| `pgbouncer` | 5433 | svc/vidya-pgbouncer:5432 | psql -p 5433 |
| `redis` | 6380 | svc/vidya-redis:6379 | redis-cli -p 6380 |
| `ingress` | 8088 | svc/ingress-nginx-controller:80 | http://vidya.127.0.0.1.nip.io:8088/ |

```powershell
# Show all mappings
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service list

# Forward API
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service api

# Forward full ingress (access both frontend and API via hostname)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service ingress
# Then open: http://vidya.127.0.0.1.nip.io:8088/

# Override local port
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service postgres -LocalPort 5450
```

> **Note:** To access the full application via ingress with correct routing, use `-Service ingress`
> which forwards to the nginx ingress controller. All routes (`/api/v1/`, `/`) work correctly.

---

## 5. kind-restart.ps1 — Rolling Restart

Triggers a `kubectl rollout restart` for the named service. Causes a brief pod replacement.

**Use when:** pod is stuck, image needs to be reloaded after a push, or env/secret changes need picking up.

```powershell
# Restart the API (common after code push)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-restart.ps1 -Service api

# Restart with extended timeout (large images, slow nodes)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-restart.ps1 -Service worker -TimeoutSeconds 180
```

**Flow:**
1. Shows current pod state
2. Prompts: type `confirm-restart` to proceed
3. Triggers `kubectl rollout restart`
4. Waits for rollout to complete
5. Shows final pod state
6. Prints rollback command

**Rollback if needed:**
```powershell
# Undo the last restart (restores previous revision)
kubectl rollout undo deployment/vidya-api -n vidya-system
kubectl rollout undo statefulset/vidya-postgres -n vidya-system
```

---

## 6. Service Map

| User name | K8s resource | Type | Restartable? |
|-----------|-------------|------|--------------|
| `api` | deployment/vidya-api | Deployment | Yes |
| `frontend` | deployment/vidya-frontend | Deployment | Yes |
| `worker` | deployment/vidya-worker | Deployment | Yes |
| `worker-heavy` | deployment/vidya-worker-heavy | Deployment | Yes |
| `flower` | deployment/vidya-flower | Deployment | Yes |
| `pgbouncer` | deployment/vidya-pgbouncer | Deployment | Yes |
| `postgres` | statefulset/vidya-postgres | StatefulSet | Yes (careful) |
| `redis` | statefulset/vidya-redis | StatefulSet | Yes (careful) |
| `minio` | statefulset/vidya-minio | StatefulSet | Yes (careful) |
| `qdrant` | statefulset/vidya-qdrant | StatefulSet | Yes (careful) |

> **StatefulSet caution:** Restarting postgres/redis/minio causes momentary data unavailability.
> The API may log connection errors during the restart window. This is normal and self-recovers.

---

## 7. Common Operational Scenarios

### "A pod is crashlooping"
```powershell
# Check current state
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-status.ps1

# See crash logs
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api -Previous

# If it's an env/config issue, check secrets
kubectl get secret -n vidya-system
kubectl describe externalsecret vidya-secret -n vidya-system
```

### "API is unhealthy"
```powershell
# Run smoke test
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-smoke.ps1

# Tail API logs live
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-logs.ps1 -Service api -Follow
```

### "Access Flower to check task queues"
```powershell
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-port-forward.ps1 -Service flower
# Open: http://localhost:5556
```

### "Push a code fix and restart the API"
```powershell
# After pushing new image to GHCR and updating the tag in helm values:
kubectl set image deployment/vidya-api api=ghcr.io/your-org/vidya-api:<new-tag> -n vidya-system

# Or restart to force pull (only if imagePullPolicy: Always)
powershell -ExecutionPolicy Bypass -File infra\scripts\kind-restart.ps1 -Service api
```

### "Monthly restore drill"
```powershell
# See backup-restore-runbook.md for the full procedure
powershell -ExecutionPolicy Bypass -File infra\scripts\local-backup.ps1
powershell -ExecutionPolicy Bypass -File infra\scripts\local-restore-drill.ps1 -PostgresTestRestore
```
