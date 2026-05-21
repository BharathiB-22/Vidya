# Vidya — Production Readiness Checklist

**Phase:** H-05 Production Hardening  
**Status:** PENDING SIGN-OFF  
**Owner:** Srinivas / Fidelitus Corp  
**Prepared by:** Engineering (H05-01 → H05-11)  
**Last updated:** 2026-05-21

> Each item is either VERIFIED (automated gate or code inspection) or  
> PENDING SRINIVAS (requires a manual action by Srinivas before staging deploy).  
> No tenant can be onboarded until every PENDING SRINIVAS item is resolved.

---

## Section 1 — Infrastructure

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 1.1 | Helm lint passes on all 4 overlays (dev / staging / prod / selfhosted) | VERIFIED | CI helm-lint job; `infra/helm/vidya/lint.sh` |
| 1.2 | `.gitignore` blocks `values.*.secret.yaml` and `infra/k8s/*.secret.yaml` | VERIFIED | H05-01 commit c5a2f87; `git check-ignore` confirmed |
| 1.3 | Container images tagged with SHA (not `:latest`) in staging/prod `values.yaml` | VERIFIED | H05-04 commit df38682; lint.sh `:latest` check active |
| 1.4 | MinIO image pinned to fixed release (not `:latest`) | VERIFIED | `values.yaml`: `RELEASE.2024-11-07T00-52-20Z` |
| 1.5 | KIND dev cluster accessible at `http://vidya.127.0.0.1.nip.io:9080` after clean recreate | VERIFIED | H03/KIND-10; hostPort 9080/9443 in `kind-config.yaml` |
| 1.6 | `values.prod.yaml` CHANGE_ME fields filled before first staging deploy | **PENDING SRINIVAS** | `postgresHost`, `redisAddress`, `s3Endpoint`, `vault.addr` |
| 1.7 | `values.staging.yaml` CHANGE_ME fields filled before first staging deploy | **PENDING SRINIVAS** | Same set of infrastructure endpoints |

---

## Section 2 — Secrets and Security

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 2.1 | JWT_SECRET_KEY rotated — old key committed in git pre-H05-01 is revoked | **PENDING SRINIVAS** | H05-01 CLAUDE.md cleanup; new key must be set in Vault |
| 2.2 | GEMINI_API_KEY rotated or revoked — key committed in git pre-H05-01 | **PENDING SRINIVAS** | H05-01 CLAUDE.md cleanup; rotate in Google Cloud console |
| 2.3 | GROQ_API_KEY rotated if it was ever committed or logged | **PENDING SRINIVAS** | Verify in git history; rotate in Groq console if found |
| 2.4 | Vault ClusterSecretStore template present for staging/self-hosted | VERIFIED | `infra/k8s/secret-store-vault.yaml.example`; H05-01 |
| 2.5 | `infra/helm/vidya/values.*.secret.yaml` never committed | VERIFIED | `.gitignore` rule active; H05-01 |
| 2.6 | ESO + Vault secret injection path documented | VERIFIED | `infra/docs/secrets-rotation.md` |

---

## Section 3 — TLS / Network / Headers

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 3.1 | TLS termination via cert-manager in staging/prod ingress | VERIFIED | `values.staging.yaml` / `values.prod.yaml` ingress TLS block; H05-05 |
| 3.2 | HSTS header enforced (`max-age=31536000; includeSubDomains`) | VERIFIED | `SecurityHeadersMiddleware`; H05-05 commit d985877 |
| 3.3 | Security headers present: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, CSP | VERIFIED | `SecurityHeadersMiddleware` |
| 3.4 | CORS `allow_origins` does not contain `*` in production config | VERIFIED | `config.py` CORS guard rejects `*` when `ENVIRONMENT=production` |
| 3.5 | SSL redirect active for staging/prod (HTTP → HTTPS) | VERIFIED | Ingress annotation `ssl-redirect: "true"` behind environment flag |

---

## Section 4 — Rate Limiting

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 4.1 | Global API rate limit: **600 requests/minute** per IP | VERIFIED | `rate_limiting.py` `default_limits=["600/minute"]`; accommodates shared NAT environments |
| 4.2 | Login endpoint: **5 requests/minute** per IP | VERIFIED | `@limiter.limit("5/minute")` on `/auth/login` and `/platform/auth/login` |
| 4.3 | Token refresh: **10 requests/minute** per IP | VERIFIED | `@limiter.limit("10/minute")` on `/auth/refresh` |
| 4.4 | OTP request: **3 requests/15 minutes** per IP | VERIFIED | `@limiter.limit("3/15minute")` on password reset OTP |
| 4.5 | Heavy AI generation endpoints (program/syllabus/exam/course kit): **5 requests/minute** per IP | VERIFIED | `@limiter.limit("5/minute")` on all generation routes |
| 4.6 | Lighter inline AI endpoints (research guide): **10 requests/minute** per IP | VERIFIED | `@limiter.limit("10/minute")` on research guidance route |
| 4.7 | Rate-limit exceeded response: `{"error": "RATE_LIMITED", "message": "Too many requests"}` | VERIFIED | `rate_limit_handler` in `main.py` |

---

## Section 5 — Error Responses

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 5.1 | All HTTP errors return `{"error": "<CODE>", "message": "<text>"}` — no `detail` wrapper, no stack traces | VERIFIED | `http_exception_handler` in `main.py`; H05-05 |
| 5.2 | Validation errors return `{"error": "VALIDATION_ERROR", "detail": [...]}` — no internal paths | VERIFIED | `validation_error_handler` in `main.py` |
| 5.3 | Unhandled exceptions return `{"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"}` | VERIFIED | `generic_exception_handler` in `main.py` |
| 5.4 | SQLAlchemy error messages not leaked to clients | VERIFIED | All DB errors caught by generic handler; H05-05 |
| 5.5 | AI provider error messages not leaked to clients | VERIFIED | AI routes catch provider exceptions and return generic errors |

---

## Section 6 — Multi-tenancy and RBAC

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 6.1 | `verify_tenant_match` enforced: JWT `schema_name` must match `X-Tenant-Slug` resolution | VERIFIED | H05-07 commit 7247d26; `dependencies.py` |
| 6.2 | SUPER_ADMIN JWT carries no `schema_name` — tenant scoping skipped | VERIFIED | `verify_tenant_match` SUPER_ADMIN exemption |
| 6.3 | `resolve_tenant` rejects slugs with ASCII control chars (null byte injection prevention) | VERIFIED | H05-07; `dependencies.py` |
| 6.4 | Missing `Authorization` header returns 401 (not 422) | VERIFIED | H05-07; `get_current_user` guard |
| 6.5 | Cross-tenant token use returns 403 `TENANT_MISMATCH` | VERIFIED | H05-07; 57 RBAC hardening tests |
| 6.6 | RBAC hardening test suite: 57 integration tests across 10 categories | VERIFIED | `test_rbac_hardening.py`; all pass |
| 6.7 | No AI endpoint applies grade / penalty / rejection autonomously | VERIFIED | Code review; human ratification step required in all consequential flows |

---

## Section 7 — Audit Log

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 7.1 | `audit_logs` table has DB-level immutability: triggers block UPDATE, DELETE, TRUNCATE | VERIFIED | H05-06 commit 45afdd9; migration `0005pub`; 9 integration tests |
| 7.2 | All AI outputs logged with: model, prompt_hash, output_summary, confidence_score | VERIFIED | `AuditService.log` called in every AI generation path |
| 7.3 | Tenant provisioned / updated / deactivated events logged | VERIFIED | H05-03; `TenantService` audit calls |
| 7.4 | Auth events logged: login, logout, token refresh, reuse detection | VERIFIED | `AuthService` audit calls |
| 7.5 | Partial tenant restore never touches `audit_logs` (append-only at restore layer too) | VERIFIED | H05-09 `restore-postgres.sh` comment + logic |

---

## Section 8 — CI/CD Pipeline

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 8.1 | PR gate runs: ruff lint, tsc type-check, pip-audit (HIGH/CRITICAL fail), npm audit (production), pytest, helm lint | VERIFIED | `.github/workflows/ci.yml`; H05-08 commit 04dec29 |
| 8.2 | CD pipeline adds: migration dry-run (destructive DDL scan + apply + rollback + re-upgrade) | VERIFIED | `.github/workflows/cd.yml`; `infra/scripts/migration-check.sh` |
| 8.3 | CD pipeline builds and pushes to `ghcr.io/BharathiB-22/vidya/api:<sha>` and `frontend:<sha>` | VERIFIED | `cd.yml` build-push matrix |
| 8.4 | Staging deploy and staging smoke test gated behind `workflow_dispatch` | VERIFIED | `cd.yml`; requires `KUBE_CONFIG_STAGING` secret |
| 8.5 | `KUBE_CONFIG_STAGING` GitHub secret configured | **PENDING SRINIVAS** | Set in GitHub repo Settings → Secrets → Actions |
| 8.6 | Rollback runbook documented | VERIFIED | `infra/docs/rollback-runbook.md` |

---

## Section 9 — Backup and Recovery

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 9.1 | 4 backup CronJobs defined: postgres (20:00), minio (20:30), qdrant (21:00), vault (21:30) UTC | VERIFIED | H05-09 `cronjobs.yaml`; `backup.enabled: true` in `values.prod.yaml` |
| 9.2 | All backups write SHA-256 checksum manifests | VERIFIED | H05-09 backup scripts |
| 9.3 | `VidyaBackupStale` Prometheus alert fires if no completed backup in 25h | VERIFIED | `prometheusrule.yaml`; H05-09 |
| 9.4 | Restore drill script with 3 human gates, smoke checks, and RTO measurement | VERIFIED | `infra/scripts/restore-drill.sh`; H05-09 |
| 9.5 | RTO target: ≤ 4 hours documented and measured in drill | VERIFIED | `infra/docs/backup-restore-runbook.md` |
| 9.6 | RPO target: ≤ 24 hours (daily backups) documented | VERIFIED | Backup-restore runbook |
| 9.7 | Monthly drill protocol documented | VERIFIED | Backup-restore runbook |
| 9.8 | `audit_logs` excluded from per-tenant partial restore | VERIFIED | `restore-postgres.sh` logic; non-negotiable rule |

---

## Section 10 — Monitoring and Observability

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 10.1 | `/metrics` returns Prometheus text format (`text/plain; version=0.0.4`) | VERIFIED | H05-10 `router.py` `generate_latest(REGISTRY)` |
| 10.2 | Custom `vidya_` metrics: `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_progress`, `auth_failures_total` | VERIFIED | H05-10 `prometheus_metrics.py` |
| 10.3 | Celery metrics: `vidya_celery_tasks_total`, `vidya_celery_task_duration_seconds`, `vidya_celery_queue_depth` | VERIFIED | H05-10 `celery_logging.py` |
| 10.4 | `vidya_dependency_health` gauge: postgres / redis / minio / qdrant (1=healthy, 0=unhealthy, -1=skipped) | VERIFIED | H05-10 `health.py` |
| 10.5 | 7 PrometheusRules in 3 groups (vidya.api, vidya.celery, vidya.kubernetes) | VERIFIED | H05-10 `prometheusrule.yaml` |
| 10.6 | `startupProbe` on API pod: 60s dev, 120s prod | VERIFIED | H05-10 `deployment.yaml` |
| 10.7 | Structured JSON logging with PII masking active | VERIFIED | H05-10 `setup_logging`; `SensitiveFieldFilter` |
| 10.8 | Path normalisation caps label cardinality (UUIDs stripped from metric labels) | VERIFIED | H05-10 `normalize_path()` |
| 10.9 | Monitoring tests: 53/53 pass | VERIFIED | H05-10 test suite |

---

## Section 11 — Onboarding and Provisioning

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 11.1 | Super Admin portal live at `/admin/tenants` (list, create, detail, retry) | VERIFIED | H05-03 commit 8cc6982; `AdminAuthGuard` + 3 pages |
| 11.2 | Password complexity enforced: uppercase + lowercase + digit + special char | VERIFIED | H05-03 `_validate_password_complexity` |
| 11.3 | Retry endpoint: `POST /tenants/{id}/retry` for FAILED tenants; guards state, logs audit | VERIFIED | H05-03 `TenantService.retry_provisioning` |
| 11.4 | Welcome email dispatched (fire-and-forget Celery) after successful provisioning | VERIFIED | H05-03 `_dispatch_welcome_email` |
| 11.5 | Provisioning lifecycle: PROVISIONING → ACTIVE / FAILED (visible in admin portal) | VERIFIED | H05-03; `TenantStatus` enum |
| 11.6 | Tenant provisioning tests: 42/42 pass | VERIFIED | H05-03 test suite |
| 11.7 | Demo quick-fill buttons on login page gated to non-production environments | **PENDING SRINIVAS** | `LoginPage.tsx` `DEMO_USERS` block should be conditionally rendered based on `VITE_ENVIRONMENT != production` env var, or removed before first commercial onboarding |
| 11.8 | PRD target: first institution onboarded in ≤ 15 minutes via Super Admin UI | VERIFIED (design) | Provisioning is synchronous Alembic + admin seed; no manual steps required |

---

## Section 12 — Known Deferred Items (Post-H05)

These items are tracked, not blocking, and must be resolved before first commercial onboarding:

| ID | Description | Owner | Target |
|----|-------------|-------|--------|
| DEFER-01 | `on_event` startup deprecation warning (FastAPI lifespan refactor) | Engineering | Before Phase 1 go-live |
| DEFER-02 | Integration test suite requires clean DB state to pass fully; stale schemas from prior runs cause intermittent failures | Engineering | Before Phase 1 go-live |
| DEFER-03 | Pricing/plan-type model (OQ-06 in PRD) — `contact_email` field exists, plan tier not yet modelled | Product + Engineering | Before first commercial onboarding |
| DEFER-04 | Staging cluster kubeconfig (`KUBE_CONFIG_STAGING`) — staging deploy pipeline inactive until this is set | Srinivas | Before staging deploy |
| DEFER-05 | `VITE_ENVIRONMENT` variable + conditional rendering of demo quick-fill buttons | Engineering | Before first demo to external institution |

---

## Section 13 — Sign-off

### Actions required from Srinivas before staging deploy

- [ ] **Rotate JWT_SECRET_KEY** — old key was committed in git pre-H05-01; generate a new key and store in Vault
- [ ] **Rotate GEMINI_API_KEY** — committed in git pre-H05-01; revoke in Google Cloud console and issue a new key
- [ ] **Rotate GROQ_API_KEY** — verify in git history (`git log -S "gsk_"`); rotate in Groq console if found in any commit
- [ ] **Set `KUBE_CONFIG_STAGING`** — base64-encoded kubeconfig for staging cluster → GitHub repo Settings → Secrets → Actions
- [ ] **Fill `values.prod.yaml` CHANGE_ME fields**: `pgbouncer.postgresHost`, `keda.redisAddress`, `backup.s3Endpoint`, `vault.addr`
- [ ] **Fill `values.staging.yaml` CHANGE_ME fields**: same set
- [ ] **Confirm first institution contact** — name, admin email, domain slug for first onboarding dry-run on staging

### Engineering sign-off (pre-Srinivas review)

All H05 steps complete as of 2026-05-21:

| Step | Commit | Tests |
|------|--------|-------|
| H05-01 Environment separation | c5a2f87 | Helm lint PASS |
| H05-02 Secrets/Vault hardening | f73e943 | Manual review PASS |
| H05-04 Demo assumption removal | df38682 | Helm lint PASS |
| H05-05 Security/CORS/rate limits | d985877 | Integration PASS |
| H05-06 Audit log immutability | 45afdd9 | 9 integration tests PASS |
| H05-07 RBAC hardening | 7247d26 | 57+12 tests PASS |
| H05-08 CI/CD pipeline | 04dec29 | Workflow lint PASS |
| H05-09 Backup/restore drills | aa2f9d4 | Scripts validated |
| H05-10 Monitoring/alerting | cae5344 | 53 tests PASS |
| H05-03 Onboarding/provisioning | 8cc6982 | 42 tests PASS |
| H05-11 Production readiness | — | DEF-01/DEF-02 resolved |

**Engineering sign-off date:** 2026-05-21  
**Srinivas sign-off date:** ___________
