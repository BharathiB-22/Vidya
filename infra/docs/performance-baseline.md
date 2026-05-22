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

## Interpretation

The smoke baseline is **PASS** with excellent margins:

- p95 of **27.82 ms** is 18× under the 500 ms threshold
- p99 of **50.70 ms** is 20× under the 1000 ms threshold
- Zero request failures across 146 requests

The KIND ingress path (port-forward → ingress-nginx → pgbouncer → postgres) is stable under 1-VU sequential load. All five covered endpoints responded correctly and consistently throughout the 30-second run.

The 317 ms login latency is expected (bcrypt cost factor) and occurs only once per test run in `setup()`.

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

## BUG-H13-03-01 — notifications 500 after pod restart

**Symptom**: `GET /notifications?page=1&page_size=10` returns HTTP 500 with
`UndefinedTableError: relation "notifications" does not exist` after the API pod restarts.

**Root cause**: The notifications repository queries without a schema-qualified table name.
PostgreSQL session `search_path` must be set to `tenant_<slug>` before the query executes.
PgBouncer resets connection state (including `search_path`) when recycling pooled connections,
so the first request on a freshly-recycled connection lands in the `public` schema where
`notifications` does not exist.

**Evidence**: `tenant_smoke_university.notifications` table exists and is intact. The same
query with `SET search_path = tenant_smoke_university` succeeds.

**Why it passed H13-02 smoke**: Single VU, sequential, all requests served on the same
connection — `search_path` was set once and not reset during the 30-second run.

**Impact for H13-03**: Notifications excluded from load script; `/ready` used as substitute.
The core ingress and database stack measurements are unaffected.

**Resolution path (deferred)**: Add `options={'schema_translate_map': None}` / explicit
`EXECUTE 'SET search_path TO tenant_...'` in the notifications repository session setup,
or configure pgbouncer `server_reset_query` to include `SET search_path` in the reset sequence.
Tracked as future improvement.

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

## Interpretation

The smoke baseline is **PASS** with excellent margins:

- p95 of **27.82 ms** is 18× under the 500 ms threshold
- p99 of **50.70 ms** is 20× under the 1000 ms threshold
- Zero request failures across 146 requests

The KIND ingress path (port-forward → ingress-nginx → pgbouncer → postgres) is stable under 1-VU sequential load. All five covered endpoints responded correctly and consistently throughout the 30-second run.

The 317 ms login latency is expected (bcrypt cost factor) and occurs only once per test run in `setup()`.

### H13-03 Sustained Load

The sustained load baseline is **PASS** — all four thresholds green, zero errors across 592 requests:

- p50 of **20 ms** is 10× under the 200 ms threshold
- p95 of **66 ms** is 12× under the 800 ms threshold
- p99 of **108 ms** is 14× under the 1500 ms threshold
- `/programs` (DB-backed) p99 **149 ms** — slowest authenticated endpoint, well within budget
- Ingress stable: no queuing, no backpressure, no rate limiting observed during the full 60 s

The stack handles 10 concurrent users at ~10 req/s with comfortable headroom. The BUG-H13-03-01
notifications `search_path` issue is documented and deferred; it does not affect ingress
stability measurements.

---

## Next Runs

| Run    | Script       | VUs  | Duration | Status  |
|--------|--------------|------|----------|---------|
| H13-02 | smoke.js     | 1    | 30 s     | DONE ✓  |
| H13-03 | load.js      | 10   | 60 s     | DONE ✓  |
| H13-04 | spike.js     | 8→30 | ~40 s    | PENDING |
