# Rollback Runbook — Vidya Staging

## When to roll back

Roll back when any of the following occur after a deploy:
- Staging smoke tests fail (`/healthz`, `/ready`, or frontend `/` do not return 200)
- Pod crash loops observed (`kubectl get pods -n vidya-system`)
- Critical errors spike in logs
- Functional regression confirmed by manual testing

---

## Automatic rollback — `helm upgrade --atomic`

Every CD pipeline deploy uses `--atomic`. If **any pod fails to reach Running/Ready** within the timeout, Helm automatically rolls back to the previous successful release.

No manual action needed — check the GitHub Actions workflow log for the rollback confirmation line:

```
Error: UPGRADE FAILED: ... rolled back release vidya to version N
```

Verify the rollback completed:
```bash
helm history vidya -n vidya-system
kubectl get pods -n vidya-system
```

---

## Manual rollback procedure

Use when you need to roll back independently of the CI/CD pipeline.

### Step 1 — Identify the target revision

```bash
helm history vidya -n vidya-system
```

Output example:
```
REVISION  STATUS      CHART        DESCRIPTION
1         superseded  vidya-0.1.0  Install complete
2         superseded  vidya-0.1.0  Upgrade complete
3         deployed    vidya-0.1.0  Upgrade complete   ← current
```

Roll back to revision 2:

```bash
helm rollback vidya 2 -n vidya-system --wait
```

`--wait` blocks until all pods from revision 2 are healthy. Add `--timeout=5m` if the cluster is slow.

### Step 2 — Verify rollback

```bash
kubectl rollout status deployment/vidya-api -n vidya-system
kubectl rollout status deployment/vidya-frontend -n vidya-system
curl -f https://staging.vidya.fidelitus.com/healthz
curl -f https://staging.vidya.fidelitus.com/ready
```

### Step 3 — Confirm image SHA

```bash
kubectl get deployment vidya-api -n vidya-system \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
```

The SHA in the image tag should match the git SHA of the revision you rolled back to.

---

## Scenario reference

| Scenario | Recovery |
|---|---|
| Pods fail to start after deploy | `--atomic` auto-rolls back; check pipeline log for confirmation |
| Manual rollback needed | `helm rollback vidya <revision> -n vidya-system --wait` |
| Migration failure (Helm hook fails) | Helm upgrade aborts before new pods start; fix migration, re-push to master |
| Migration applied but code fails | Helm rollback restores old code; DB schema may be ahead — assess if forward-only or requires downgrade |
| GHCR push failed — old image still live | Previous SHA tag still deployed in staging; re-trigger CD `workflow_dispatch` |
| Smoke test fails post-deploy | `helm rollback vidya -n vidya-system --wait`, then investigate |

---

## Migration rollback

**Helm rollback does not revert database migrations.** If a migration was applied by the `migrate` Helm hook, it persists in the database after a Helm rollback.

Before triggering a Helm rollback, assess whether:

1. **Schema change is backwards-compatible** — old code can run against the new schema (e.g., new nullable column added). In this case, Helm rollback is safe without a DB migration rollback.

2. **Schema change is breaking** — old code cannot run against the new schema (e.g., column renamed or type changed). In this case, a manual DB migration downgrade is required first:

```bash
# Connect to the CI or staging database
ALEMBIC_TARGET=public alembic downgrade -1

# If tenant schemas also need rollback (run per schema):
ALEMBIC_TARGET=tenant TENANT_SCHEMA=<schema_name> alembic downgrade -1
```

Then perform the Helm rollback.

**Never run `alembic downgrade base`** — this destroys all schema history.

---

## Production deployment order (informational)

The Helm chart enforces safe ordering automatically:

1. `migrate` Job runs as `pre-upgrade` hook (before any pod restart)
2. Migration `backoffLimit: 0` — fail fast, never partial state
3. New pods start only after migration exits 0
4. PodDisruptionBudgets (`minAvailable: 2` for API in prod) prevent total outage during rolling update
5. `--atomic` on every `helm upgrade` call ensures automatic rollback on pod failure

---

## Useful commands

```bash
# Current release status
helm status vidya -n vidya-system

# All revisions
helm history vidya -n vidya-system

# Pod status
kubectl get pods -n vidya-system

# API pod logs (latest)
kubectl logs -l app.kubernetes.io/component=api -n vidya-system --tail=100

# Alembic version in DB
psql $DATABASE_URL -c "SELECT * FROM alembic_version;"
```
