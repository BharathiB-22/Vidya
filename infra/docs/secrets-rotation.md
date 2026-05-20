# Vidya Secrets Rotation Guide

Owner: Srinivas / Fidelitus Corp  
Applies to: staging and prod environments using ESO + Vault  
Dev path: edit `infra/helm/vidya/values.dev.yaml` (or `values.dev.secret.yaml`) and re-deploy.

---

## How rotation works

All secrets live in a single Vault KV v2 entry per environment:

```
secret/data/vidya/staging   (all staging secrets as fields)
secret/data/vidya/prod      (all prod secrets as fields)
```

ESO polls Vault on the `refreshInterval` (1 h staging, 30 min prod) and writes the current Vault values into the Kubernetes Secret `vidya-secret`. Pods read this Secret at container startup. **Pods do not restart automatically when the Secret changes** — a rolling restart is required to pick up new values for secrets that are read once at startup.

**General rotation procedure:**
1. Write the new value to Vault (`vault kv patch`)
2. Wait for ESO refresh, or force it (see below)
3. Rolling-restart the affected pods

**Force ESO re-sync immediately:**
```bash
kubectl annotate externalsecret vidya-secret \
  force-sync=$(date +%s) -n vidya-system --overwrite
```

**Verify sync succeeded:**
```bash
kubectl describe externalsecret vidya-secret -n vidya-system
# Status.Conditions[0].Type=Ready, Reason=SecretSynced
```

**Verify the Kubernetes Secret received the new value (first 8 chars):**
```bash
kubectl get secret vidya-secret -n vidya-system \
  -o jsonpath='{.data.JWT_SECRET}' | base64 -d | head -c 8
```

---

## ESO health verification checklist

Run this after every rotation or deploy:

```bash
# 1. ExternalSecret must be Ready
kubectl describe externalsecret vidya-secret -n vidya-system | grep -A5 Conditions
# Expected: Type=Ready, Status=True, Reason=SecretSynced

# 2. Secret must exist and have all expected keys
kubectl get secret vidya-secret -n vidya-system -o json | \
  jq '.data | keys'
# Expected: 14 keys including DATABASE_URL, JWT_SECRET, EXAM_FERNET_KEY, etc.

# 3. Spot-check a known-non-empty secret (JWT_SECRET is always set)
kubectl get secret vidya-secret -n vidya-system \
  -o jsonpath='{.data.JWT_SECRET}' | base64 -d | wc -c
# Expected: >= 64 characters

# 4. Pods are running (no CrashLoopBackOff from bad secrets)
kubectl get pods -n vidya-system
```

---

## Secret-by-secret rotation procedures

### JWT_SECRET

**What it is:** HMAC key signing all user JWTs. Rotating it invalidates every active session — all logged-in users are signed out.

**Generation:**
```bash
openssl rand -hex 32   # produces 64-char hex string
```

**Minimum length:** 64 characters. Shorter values are accepted by the app but weaken security.

**Vault update:**
```bash
vault kv patch secret/vidya/prod JWT_SECRET="<new-64-char-hex>"
```

**Pods that need restart:** `vidya-api` (reads JWT_SECRET at startup for the signing key).

**Operational impact:**
- All existing JWTs are immediately invalid after the pod restart
- Users must log in again — access tokens and refresh tokens both invalidate
- No data loss; only session disruption
- Schedule during low-traffic hours (IST 22:00–07:00 matches off-peak scaling window)

**Follow-up (H05-05 scope):** Add startup validation that rejects JWT_SECRET shorter than 64 characters or matching known placeholder patterns (`dev-jwt`, `CHANGE_ME`, `secret`).

---

### EXAM_FERNET_KEY

**What it is:** Fernet symmetric key used to encrypt exam paper payloads at rest in the database. Rotating it breaks decryption of all existing sealed exam records.

**Generation:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**CRITICAL — key migration required before rotation:**
Unlike JWT_SECRET, rotating EXAM_FERNET_KEY without re-encrypting existing records makes existing sealed exams permanently unreadable. Procedure:

1. Write a one-off migration script that reads all `ExamPaper` records encrypted with the old key, decrypts them, and re-encrypts with the new key.
2. Run the migration against a snapshot/backup first.
3. Only then update Vault and restart pods.

**Do not rotate this key without first completing step 1.** Coordinate with Srinivas before any rotation.

**Operational impact:** Exam decryption fails for all sealed papers until pods restart with the new key AND all records are re-encrypted.

**Follow-up (H05-05 scope):** Add startup validation that rejects EXAM_FERNET_KEY values that are not valid Fernet key format (44-char base64url ending in `=`).

---

### DATABASE_URL password (POSTGRES_PASSWORD)

**What it is:** PostgreSQL superuser password for the `vidya` database user. Changing it breaks all DB connections until pods restart.

**Rotation sequence (order matters):**
1. Update the password in managed PostgreSQL (Cloud SQL, RDS, etc.)
2. Update `POSTGRES_PASSWORD` and `DATABASE_URL` in Vault:
   ```bash
   NEW_PASS="<new-password>"
   NEW_URL="postgresql+asyncpg://vidya:${NEW_PASS}@db-host:5432/vidya"
   vault kv patch secret/vidya/prod \
     POSTGRES_PASSWORD="${NEW_PASS}" \
     DATABASE_URL="${NEW_URL}"
   ```
3. Force ESO re-sync, then restart `vidya-api`, `vidya-worker`, `vidya-worker-heavy`, `vidya-pgbouncer`.

**PgBouncer note:** PgBouncer reads `DB_PASSWORD` from the Kubernetes Secret at startup. It does NOT dynamically reload. A restart is mandatory.

**Operational impact:** All DB-dependent operations fail between the PostgreSQL password change and the pod restart. Keep the window under 2 minutes.

---

### Redis password (REDIS_PASSWORD)

**What it is:** Redis `requirepass` auth password. Changing it breaks Celery task queuing and the Flower monitoring UI.

**Rotation sequence:**
1. Update `requirepass` in managed Redis (Azure Cache, ElastiCache, etc.) or the Redis config.
2. Update Vault:
   ```bash
   NEW_PASS="<new-password>"
   NEW_URL="redis://:${NEW_PASS}@redis-host:6379/0"
   vault kv patch secret/vidya/prod \
     REDIS_PASSWORD="${NEW_PASS}" \
     REDIS_URL="${NEW_URL}"
   ```
3. Force ESO re-sync, then restart `vidya-api`, `vidya-worker`, `vidya-worker-heavy`, `vidya-flower`.

**KEDA TriggerAuthentication note:** KEDA reads `REDIS_PASSWORD` from the same Secret. Running KEDA ScaledObjects may behave erratically if the password changes without a pod restart. KEDA does not automatically reload credentials.

**Operational impact:** Celery task queuing is unavailable during the credential gap. Existing in-flight tasks may fail. Do not rotate Redis credentials while a long-running AI generation job is active.

---

### MinIO credentials (S3_ACCESS_KEY / S3_SECRET_KEY)

**What it is:** MinIO root user/password used for all object storage operations (file uploads, course kit exports, learning material packages).

**Generation:** Any strong random string (32+ characters).

**Rotation sequence:**
1. Update MinIO root credentials via the MinIO console or `mc admin user` CLI.
2. Update Vault:
   ```bash
   vault kv patch secret/vidya/prod \
     S3_ACCESS_KEY="<new-key>" \
     S3_SECRET_KEY="<new-secret>"
   ```
3. Force ESO re-sync, then restart `vidya-api`, `vidya-worker`, `vidya-worker-heavy`.

**Operational impact:** File uploads and downloads fail during the credential gap. In-progress multipart uploads will fail. Storage access is restored immediately after the pod restart.

---

### AI provider keys (GEMINI_API_KEY / GROQ_API_KEY)

**What it is:** API keys for Gemini and Groq LLM providers. These are pure stateless HTTP credentials — rotation has no impact on existing data.

**When to rotate:** Monthly recommended. Immediately if the key is exposed (logged, committed, or shared accidentally).

**Vault update:**
```bash
vault kv patch secret/vidya/prod GEMINI_API_KEY="<new-key>"
vault kv patch secret/vidya/prod GROQ_API_KEY="<new-key>"
```

**Pods that need restart:** `vidya-api`, `vidya-worker`, `vidya-worker-heavy` (all read AI keys at startup).

**Operational impact:** AI generation (program advice, syllabus generation, etc.) fails between the key change and pod restart. Zero data loss. Safe to rotate any time.

**Note:** Revoke the old key in the provider console AFTER the pod restart completes and you have verified the new key works. Do not revoke first.

---

### Flower password (FLOWER_PASSWORD)

**What it is:** Basic-auth password for the Flower Celery monitoring UI. Changing it does not affect task processing — Flower is an observer only.

**Vault update:**
```bash
vault kv patch secret/vidya/prod FLOWER_PASSWORD="<new-password>"
```

**Pods that need restart:** `vidya-flower` only.

**Operational impact:** Flower UI is briefly unavailable during pod restart. No effect on task queuing or processing.

---

## Vault outage recovery

### What happens during a Vault outage

| Component | Behaviour |
|---|---|
| **Running pods** | Unaffected. Pods read secrets from the Kubernetes Secret at startup and never query Vault directly. |
| **ESO refresh cycle** | Fails silently. ESO logs `SecretSynced=False` but does NOT delete or modify the existing Kubernetes Secret. |
| **New pod starts** | Use the existing Kubernetes Secret (last synced value). Safe for all secrets. |
| **`helm upgrade` during outage** | Safe if not changing secrets. Unsafe if the upgrade would change secret values — ESO cannot pull new values. Do not run secret-changing upgrades during Vault downtime. |
| **KEDA ScaledObjects** | Continue operating using the existing TriggerAuthentication Secret. |

### Recovery procedure

1. **Verify Vault is reachable from the cluster:**
   ```bash
   kubectl run vault-check --image=curlimages/curl --restart=Never --rm -it -- \
     curl -s $VAULT_ADDR/v1/sys/health | grep sealed
   ```

2. **Force ESO re-sync once Vault is back:**
   ```bash
   kubectl annotate externalsecret vidya-secret \
     force-sync=$(date +%s) -n vidya-system --overwrite
   ```

3. **Verify sync succeeded:**
   ```bash
   kubectl describe externalsecret vidya-secret -n vidya-system | grep -A5 Conditions
   # Expected: Type=Ready, Status=True, Reason=SecretSynced
   ```

4. **If ESO stays in error state** (Vault came back but ESO does not re-sync):
   ```bash
   kubectl rollout restart deployment -l app.kubernetes.io/name=external-secrets \
     -n external-secrets
   ```

5. **Emergency manual secret injection** (only if Vault will be down > 2 hours and pods need rotation):
   ```bash
   # Temporarily inject secrets directly — NEVER commit this command to history
   kubectl create secret generic vidya-secret \
     --from-literal=JWT_SECRET="$(vault kv get -field=JWT_SECRET secret/vidya/prod)" \
     ... \
     -n vidya-system --dry-run=client -o yaml | kubectl apply -f -
   ```
   Remove the manual override once ESO resumes normal sync.

### Vault HA recommendation

For production, run Vault in HA mode (Raft or Consul backend) with at least 3 nodes. A single-node Vault is a single point of failure for secret rotation (not for running pods — see table above). Vault HA setup is outside Vidya's Helm chart scope; refer to HashiCorp's Vault Helm chart.

---

## GHCR image pull secret

Container images are pulled from `ghcr.io/BharathiB-22`. The cluster needs a pull secret to authenticate to the private registry.

**Create the pull secret (run once per cluster):**
```bash
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=BharathiB-22 \
  --docker-password=<github-pat-read-packages> \
  -n vidya-system
```

Generate the GitHub PAT at: `https://github.com/settings/tokens` → Classic → `read:packages` scope.

**Wire it into the Helm chart** (add to `values.staging.yaml` and `values.prod.yaml`):
```yaml
global:
  imagePullSecrets:
    - name: ghcr-pull-secret
```

**Rotation:** When the GitHub PAT expires, recreate the secret:
```bash
kubectl delete secret ghcr-pull-secret -n vidya-system
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=BharathiB-22 \
  --docker-password=<new-pat> \
  -n vidya-system
```
No pod restart needed — image pulls happen at pod scheduling time, not at runtime.

---

## Follow-up: runtime secret validation guards (H05-05 scope)

The following startup checks are deferred to H05-05 but are required before the first real institution onboarding:

| Secret | Validation rule |
|---|---|
| `JWT_SECRET` | Reject if length < 64 chars, or if value matches patterns: `dev-jwt`, `CHANGE_ME`, `secret`, `test` |
| `EXAM_FERNET_KEY` | Reject if not valid Fernet key format (44-char base64url ending in `=`) — use `Fernet(key)` constructor which raises `ValueError` on invalid keys |
| `DATABASE_URL` | Reject if hostname is `localhost` or `127.0.0.1` when `ENVIRONMENT=production` or `staging` |
| `REDIS_URL` | Same localhost guard as DATABASE_URL |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Reject empty strings when `ENVIRONMENT=production` or `staging` |
| `GEMINI_API_KEY` | Warn (not fail) if empty — some modules degrade gracefully to Groq fallback |

These guards should run in `backend/app/core/config.py` (or equivalent settings module) using a Pydantic `@validator` or `@model_validator` that raises `ValueError` on bad values. The app should refuse to start rather than start with broken secrets.
