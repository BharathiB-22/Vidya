# Vidya Load Tests

k6-based API reliability and load baseline for Vidya.

## Prerequisites

Install k6:
```powershell
# Windows — Chocolatey
choco install k6

# Or download binary from https://github.com/grafana/k6/releases
# Add to PATH
```

Verify: `k6 version`

## Target

Default target: `http://vidya.127.0.0.1.nip.io:9080/api` (KIND ingress, full production-like local stack).

KIND cluster must be running: `kubectl get pods -n vidya` — all pods healthy.

## Quick Start

```powershell
cd infra\load-tests

# 1. Smoke (1 VU, 30 s) — run this first
.\run-smoke.ps1

# 2. Sustained load (10 VU, 60 s)
.\run-load.ps1

# 3. Spike / rate-limit validation (8 → 30 VU)
.\run-spike.ps1
```

## Environment Variables

| Variable        | Default                        | Description                        |
|-----------------|--------------------------------|------------------------------------|
| `BASE_URL`      | `http://vidya.127.0.0.1.nip.io:9080/api` | API base (no trailing slash) |
| `TENANT`        | `dev`                          | Tenant slug sent in `X-Tenant-Slug` header |
| `FACULTY_EMAIL` | `faculty@dev.vidya.local`      | FACULTY user for read-only tests   |
| `FACULTY_PASS`  | `Faculty@123`                  | FACULTY password                   |
| `ADMIN_EMAIL`   | `admin@dev.vidya.local`        | ADMIN user (audit-log tests only)  |
| `ADMIN_PASS`    | `Admin@123`                    | ADMIN password                     |

Override on the command line:

```powershell
.\run-smoke.ps1 -FacultyEmail "myfaculty@tenant.local" -FacultyPass "Secret99"
```

Or pass directly to k6:

```powershell
k6 run -e BASE_URL=http://custom:9080/api -e TENANT=myorg smoke.js
```

## Save Results

```powershell
.\run-smoke.ps1 -OutFile "results\smoke-$(Get-Date -f yyyyMMdd-HHmm).json"
.\run-load.ps1  -OutFile "results\load-$(Get-Date -f yyyyMMdd-HHmm).json"
.\run-spike.ps1 -OutFile "results\spike-$(Get-Date -f yyyyMMdd-HHmm).json"
```

Results JSON files are gitignored (`results/*.json`). The `results/` directory is tracked via `.gitkeep`.

## Test Descriptions

| Script      | VUs    | Duration  | Purpose                                                  |
|-------------|--------|-----------|----------------------------------------------------------|
| `smoke.js`  | 1      | 30 s      | Verify all key endpoints return 200; establish p95/p99   |
| `load.js`   | 10     | 60 s      | Sustained baseline; measure p50/p95/p99 under real load  |
| `spike.js`  | 8→30   | ~40 s     | Trigger rate-limiter; validate 429 shape, no 5xx         |

## Thresholds

**Smoke / Load:**
- Error rate < 1 %
- p95 < 500 ms (smoke), p95 < 800 ms (load)
- p99 < 1 000 ms (smoke), p99 < 1 500 ms (load)

**Spike:**
- 5xx rate < 5 % (429s are expected, 5xx are not)
- 429 responses must contain `{"error":"RATE_LIMITED","message":"..."}` shape

## Covered Endpoints

All tests are **read-only** (no write mutations during VU loops). No AI generation endpoints.

| Endpoint                              | Tests  | Notes                          |
|---------------------------------------|--------|--------------------------------|
| `/healthz`                            | smoke  | No auth required               |
| `/ready`                              | smoke  | No auth required               |
| `/auth/login`                         | all    | Used in `setup()` only         |
| `/auth/me`                            | all    | Auth baseline                  |
| `/programs?page=1&page_size=10`       | all    | Primary read endpoint          |
| `/notifications?page=1&page_size=10` | smoke, load | Notification list         |

## Grafana Correlation

While a load test runs, open Grafana at `http://localhost:3000`:

- **Request rate**: `sum(rate(http_requests_total[30s]))`
- **Error rate**: `sum(rate(http_requests_total{status=~"5.."}[30s]))`
- **Latency p95**: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[30s]))`

Results are recorded in `infra/docs/performance-baseline.md` after each test run.
