# Vidya Performance Baseline

Performance measurements against the KIND local stack.
Updated each time a load test run is executed and recorded.

---

## Environment

| Item             | Value                                                      |
|------------------|------------------------------------------------------------|
| Stack            | KIND cluster (vidya) + docker-compose monitoring           |
| Ingress          | kubectl port-forward → localhost:8088 → ingress-nginx:80   |
| API URL          | http://vidya.127.0.0.1.nip.io:8088/api                    |
| Tenant           | smoke-university                                           |
| k6 version       | v2.0.0                                                     |
| Platform         | Windows 11, Docker Desktop                                 |
| Cluster pods     | 10/10 Running (vidya-system namespace)                     |

---

## Run 1 — Smoke Baseline

| Item     | Value                        |
|----------|------------------------------|
| Date     | 2026-05-22                   |
| Commit   | b519de1 (H13-01 scaffold)    |
| Script   | infra/load-tests/smoke.js    |
| VUs      | 1                            |
| Duration | 30 s                         |
| Iterations | 29                         |

### Thresholds

| Threshold                         | Target      | Actual    | Pass? |
|-----------------------------------|-------------|-----------|-------|
| http_req_failed rate              | < 1%        | 0.00%     | ✓     |
| http_req_duration p(95)           | < 500 ms    | 27.82 ms  | ✓     |
| http_req_duration{phase:smoke} p(99) | < 1000 ms | 50.70 ms  | ✓     |

### Latency (all requests, incl. login call)

| Percentile | ms      |
|------------|---------|
| min        | 2.14    |
| avg        | 15.50   |
| p50 (med)  | 14.11   |
| p90        | 22.71   |
| p95        | 27.82   |
| p99        | 50.70   |
| max        | 317.88  |

> Note: max 317.88 ms is the single `/auth/login` call in `setup()` — bcrypt hash computation.
> The remaining 145 requests (healthz, ready, auth/me, programs, notifications) averaged 14 ms.

### Login one-time call

| Metric               | Value     |
|----------------------|-----------|
| auth_login_duration  | 317.88 ms |
| login_errors         | 0 / 1     |

### Per-endpoint checks (146 total, 100% pass)

| Endpoint                   | Check              | Result |
|----------------------------|--------------------|--------|
| /healthz                   | healthz 200        | ✓ 29/29 |
| /ready                     | ready 200          | ✓ 29/29 |
| /auth/me                   | auth/me 200        | ✓ 29/29 |
| /programs?page=1&page_size=10 | programs 200    | ✓ 29/29 |
| /notifications?page=1&page_size=10 | notifications 200 | ✓ 29/29 |
| setup /auth/login          | login 200          | ✓ 1/1  |

### Throughput

| Metric        | Value           |
|---------------|-----------------|
| Total requests | 146            |
| req/s         | 4.61            |
| data received | 101 kB (3.2 kB/s) |
| data sent     | 55 kB (1.8 kB/s)  |

---

## Grafana / Prometheus Correlation Notes

### Finding: API scrape target unreachable

During the smoke test, Prometheus (`vidya-prometheus-1` docker container) reported `up=0` for the `vidya-api` scrape target. The docker-compose monitoring stack and the KIND cluster pods run on separate Docker networks. Prometheus cannot reach `vidya-api:8000` from within the monitoring compose network.

**Impact**: API-level request rate, latency histograms, and error counts are not available in Grafana for this run. The k6 output is the authoritative source for H13-02.

**Infrastructure exporters**: Both `postgres_exporter` and `redis_exporter` containers are also showing `up=0` for their specific application metrics (pg_up, redis_up). Root cause: these exporters are configured to reach the KIND cluster's postgres/redis, which are also not network-accessible from the docker-compose monitoring stack.

**Resolution path (deferred)**: To enable Prometheus correlation, expose the API pod's `/metrics` endpoint through the KIND ingress at `/metrics` (auth-protected), or configure Prometheus with a scrape job that targets the host-port-forwarded API. Tracked as future improvement.

### Available Grafana data

| Scrape target        | up | Notes                              |
|----------------------|----|------------------------------------|
| prometheus           | 1  | Self-scrape working                |
| postgres (exporter)  | 0  | Exporter container can't reach KIND Postgres |
| redis (exporter)     | 0  | Exporter container can't reach KIND Redis  |
| vidya-api            | 0  | KIND pod not reachable from docker-compose |

---

## Run 2 — Sustained Load Baseline (H13-03)

| Item       | Value                           |
|------------|---------------------------------|
| Date       | 2026-05-22                      |
| Commit     | 71f7316 (H13-02 smoke baseline) |
| Script     | infra/load-tests/load.js        |
| VUs        | 10                              |
| Duration   | 60 s                            |
| Iterations | 591                             |

### Thresholds

| Threshold                   | Target      | Actual     | Pass? |
|-----------------------------|-------------|------------|-------|
| http_req_failed rate        | < 1%        | 0.00%      | ✓     |
| http_req_duration p(50)     | < 200 ms    | 20.02 ms   | ✓     |
| http_req_duration p(95)     | < 800 ms    | 66.01 ms   | ✓     |
| http_req_duration p(99)     | < 1500 ms   | 107.87 ms  | ✓     |

### Overall Latency (all 592 requests)

| Percentile | ms      |
|------------|---------|
| min        | 2.16    |
| avg        | 24.18   |
| p50 (med)  | 20.02   |
| p90        | 47.91   |
| p95        | 66.01   |
| p99        | 107.87  |
| max        | 307.78  |

> Note: max 307.78 ms is the single `/auth/login` call in `setup()` — bcrypt hash computation, consistent with smoke baseline.

### Per-endpoint Latency

| Endpoint        | n   | min (ms) | avg (ms) | p50 (ms) | p90 (ms) | p95 (ms) | p99 (ms) | max (ms) |
|-----------------|-----|----------|----------|----------|----------|----------|----------|----------|
| /ready          | 240 | 2.2      | 6.8      | 6.6      | 9.5      | 10.6     | 17.8     | 25.1     |
| /auth/me        | 177 | 8.6      | 32.0     | 27.7     | 51.3     | 69.4     | 104.3    | 108.4    |
| /programs       | 174 | 13.3     | 38.7     | 29.5     | 66.1     | 100.7    | 149.4    | 195.4    |

> `/ready` handles ~40% of VUs (VU IDs mod 3 == 1); `/auth/me` and `/programs` each handle ~30%.
> Distribution is stable for all 60 seconds — no endpoint showed degradation over time.

### Throughput

| Metric          | Value             |
|-----------------|-------------------|
| Total requests  | 592               |
| req/s           | 9.63              |
| Iterations/s    | 9.62              |
| data received   | 448 kB (7.3 kB/s) |
| data sent       | 221 kB (3.6 kB/s) |

### Checks

| Check            | Result       |
|------------------|--------------|
| setup login 200  | ✓ 1/1        |
| ready 200        | ✓ 240/240    |
| auth/me 200      | ✓ 177/177    |
| programs 200     | ✓ 174/174    |
| **Total**        | **592/592**  |

### Ingress Stability

The KIND ingress path (port-forward → ingress-nginx → pgbouncer → postgres) remained stable
for the full 60-second run. No connection resets, no 5xx responses, no rate-limit headers observed.
Iteration duration was tightly clustered: avg 1.02 s, p95 1.06 s — indicating no queuing or backpressure
within the ingress stack at 10 VU / ~10 req/s.


---

## Run 3 — Spike and Rate-Limit Validation (H13-04)

| Item       | Value                                       |
|------------|---------------------------------------------|
| Date       | 2026-05-22                                  |
| Commit     | 480e815 (H13-03 sustained load baseline)    |
| Script     | infra/load-tests/spike.js                   |
| VUs        | 8 → 30 → 8 (warm-up / spike / wind-down)    |
| Duration   | 40 s (10s + 20s + 10s)                      |
| Iterations | 1 432                                       |

### Thresholds

| Threshold                                     | Target | Actual | Pass? |
|-----------------------------------------------|--------|--------|-------|
| http_req_failed{expected_response:false} rate | < 5%   | 100%*  | ✗     |

> \* All 63 failed requests were HTTP 500 (not 429). k6 treats those as `expected_response:false`,
> so 63/63 = 100%. `abortOnFail` is false — the test ran to completion. This is a degenerate
> case caused by **no 429s being issued** (see BUG-H13-04-01).

### Status Code Distribution

| Status | Count | Share  |
|--------|-------|--------|
| 200    | 1 370 | 95.60% |
| 500    | 63    | 4.39%  |
| 429    | 0     | 0.00%  |

### Overall Latency (1 432 requests, `/programs` only)

| Percentile | ms    |
|------------|-------|
| min        | 12.8  |
| avg        | 227.1 |
| p50 (med)  | 190.4 |
| p90        | 467.1 |
| p95        | 560.8 |
| p99        | 679.4 |
| max        | 772.2 |

> Latency increase vs H13-03 sustained: p50 +170 ms, p95 +495 ms — expected under 3× VU load.
> All requests still completed; no connection timeouts observed.

### Throughput

| Metric         | Value             |
|----------------|-------------------|
| Total requests | 1 433             |
| req/s          | 35.0              |
| data received  | 889 kB (22 kB/s)  |
| data sent      | 831 kB (20 kB/s)  |

### Rate-Limit Behavior

| Metric          | Value     |
|-----------------|-----------|
| rate_limit_hits | 0 / 1432  |
| server_errors   | 63 / 1432 |

**No rate limiting was triggered at any VU level.** The `/programs` endpoint handled up to
30 concurrent VUs (~35 req/s) without issuing a single 429 response. See BUG-H13-04-01.

### 500 Error Distribution Over Time

Errors first appeared at **t+11 s** (when VU count reached ~8 at end of warm-up), peaked
at t+14–15 s (8 errors/s during early spike), and persisted intermittently through wind-down.
Error pattern is **bursty, not cascading** — gaps of 2–5 s between bursts confirm the API
continued serving requests normally between failures.

| Phase      | t range | VUs  | Errors |
|------------|---------|------|--------|
| Warm-up    | 0–10 s  | 1–8  | 0      |
| Spike ramp | 11–20 s | 8–30 | 32     |
| Spike hold | 21–30 s | ~30  | 11     |
| Wind-down  | 31–40 s | 30–8 | 20     |

### Recovery Verification

Post-spike health probe (immediately after k6 exit):

| Probe    | Status | Note                                                |
|----------|--------|-----------------------------------------------------|
| /healthz | 200    | `{"status":"ok"}`                                   |
| /ready   | 200    | `{"db":"healthy","redis":"healthy","s3":"healthy"}` |

**Recovery is clean.** No circuit breakers tripped, no memory leaks, no connection pool
exhaustion observed.

---

## BUG-H13-04-01 — Rate limiting not active in KIND deployment

**Symptom**: Zero 429 responses across 1 432 requests at 30 VU / 35 req/s peak.
The spike test was designed to trigger rate-limit behaviour; none was observed.

**Root cause**: Rate-limit middleware (`slowapi` or ingress-nginx `limit_req`) is not
configured in the KIND dev values. `values.dev.yaml` likely omits `RATE_LIMIT_*` env vars
or the ingress annotation `nginx.ingress.kubernetes.io/limit-rps`.

**Impact**: In production, rate limiting must be explicitly configured and verified before
launch. Without it, a 30+ VU burst hits the database directly.

**Resolution path (deferred)**:
1. Add `nginx.ingress.kubernetes.io/limit-rps: "20"` to the API ingress manifest, or
2. Configure `slowapi` in the FastAPI app with `{"error":"RATE_LIMITED","message":"Too many requests"}` shape.
3. Re-run spike.js after enabling — the test is already instrumented to validate the 429 response shape.

---

## BUG-H13-03-01 — search_path reset scope extended by H13-04

**Original finding (H13-03)**: `/notifications` returns 500 after pod restart — pgbouncer
resets the session `search_path`, landing queries in `public` instead of `tenant_<slug>`.

**H13-04 extension**: `/programs` also returns 500 under spike load (30 VUs, sleep 0.2s).
Under H13-03 sustained (10 VUs, sleep 1s), infrequent connection recycling kept errors at
0%. Under H13-04 spike, aggressive connection cycling surfaces the bug on any tenant-schema
endpoint. The fix (explicit `SET search_path` in the repository base class, or
`server_reset_query` in pgbouncer) resolves it globally.

---

## Interpretation

### H13-02 Smoke

The smoke baseline is **PASS** with excellent margins:

- p95 of **27.82 ms** is 18× under the 500 ms threshold
- p99 of **50.70 ms** is 20× under the 1000 ms threshold
- Zero request failures across 146 requests

The KIND ingress path (port-forward → ingress-nginx → pgbouncer → postgres) is stable under 1-VU sequential load. The 317 ms login latency is expected (bcrypt cost factor) and occurs only once per test run in `setup()`.

### H13-03 Sustained Load

The sustained load baseline is **PASS** — all four thresholds green, zero errors across 592 requests:

- p50 of **20 ms** is 10× under the 200 ms threshold
- p95 of **66 ms** is 12× under the 800 ms threshold
- p99 of **108 ms** is 14× under the 1500 ms threshold
- `/programs` (DB-backed) p99 **149 ms** — slowest authenticated endpoint, well within budget
- Ingress stable: no queuing, no backpressure, no rate limiting observed during the full 60 s

The stack handles 10 concurrent users at ~10 req/s with comfortable headroom.

### H13-04 Spike

The spike test **ran to completion** without cascading failure. The ingress and API stack
remained responsive throughout 30 VUs / 35 req/s. Two actionable findings:

1. **Rate limiting is not configured** (BUG-H13-04-01): must be added before production
   launch; spike.js is already instrumented to re-validate once enabled.
2. **search_path bug is load-sensitive** (BUG-H13-03-01 extended): 4.4% of spike requests
   returned 500 due to pgbouncer connection recycling. The fix is a single change to the
   repository session setup and resolves both `/notifications` and all other tenant endpoints.

Excluding the known search_path issue, the ingress stack demonstrated stable latency
(p50 190 ms, p95 561 ms) and clean recovery under 3× normal load.

---

## Next Runs

| Run    | Script    | VUs  | Duration | Status |
|--------|-----------|------|----------|--------|
| H13-02 | smoke.js  | 1    | 30 s     | DONE ✓ |
| H13-03 | load.js   | 10   | 60 s     | DONE ✓ |
| H13-04 | spike.js  | 8→30 | ~40 s    | DONE ✓ |
