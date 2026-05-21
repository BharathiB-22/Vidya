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

## Next Runs

| Run    | Script       | VUs  | Duration | Status  |
|--------|--------------|------|----------|---------|
| H13-02 | smoke.js     | 1    | 30 s     | DONE ✓  |
| H13-03 | load.js      | 10   | 60 s     | PENDING |
| H13-04 | spike.js     | 8→30 | ~40 s    | PENDING |
