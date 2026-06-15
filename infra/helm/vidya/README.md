# Vidya Helm Chart

Kubernetes deployment for the Vidya AI-powered education platform.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start — kind (local dev)](#quick-start--kind-local-dev)
3. [Helm Install](#helm-install)
4. [Helm Upgrade](#helm-upgrade)
5. [Rollback](#rollback)
6. [Three Deployment Paths](#three-deployment-paths)
7. [Secrets Management](#secrets-management)
8. [Production Readiness Checklist](#production-readiness-checklist)

---

## Prerequisites

Install these components **before** running `helm install`. The chart does not
manage cluster-level prerequisites.

### cert-manager

Handles TLS certificate issuance. Required when `ingress.tls: true`.

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set crds.enabled=true
```

Create a ClusterIssuer after installation:

```yaml
# infra/k8s/cluster-issuer-letsencrypt-staging.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: you@example.com
    privateKeySecretRef:
      name: letsencrypt-staging
    solvers:
      - http01:
          ingress:
            class: nginx
```

```bash
kubectl apply -f infra/k8s/cluster-issuer-letsencrypt-staging.yaml
```

### ingress-nginx

Handles HTTP/HTTPS routing into the cluster.

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace
```

For **kind** local dev, add `--set controller.hostPort.enabled=true` so port
80 and 443 on localhost forward to the ingress controller.

### KEDA

Kubernetes Event-driven Autoscaler — required for worker ScaledObjects.

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda \
  --namespace keda --create-namespace
```

### External Secrets Operator

Required only when `externalSecrets.enabled: true` (staging and prod).

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace
```

After installation, create a SecretStore or ClusterSecretStore that references
your secrets backend (Vault, AWS Secrets Manager, GCP Secret Manager, etc.).
The store name must match `externalSecrets.storeName` in your values overlay.

---

## Quick Start — kind (local dev)

### 1. Create the kind cluster

```bash
# Requires kind ≥ 0.23 and Docker
kind create cluster --config infra/helm/kind-config.yaml --name vidya-dev
```

The kind config maps host ports 80 → 30080 and 443 → 30443 on the control-
plane node so ingress-nginx receives traffic on the standard HTTP ports.

### 2. Install ingress-nginx with host-port support

```bash
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.hostPort.enabled=true \
  --set controller.service.type=NodePort \
  --set controller.service.nodePorts.http=30080 \
  --set controller.service.nodePorts.https=30443
```

Wait for the controller to be ready:

```bash
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx
```

### 3. Install KEDA

```bash
helm install keda kedacore/keda --namespace keda --create-namespace
```

### 4. Install the Vidya chart

```bash
helm install vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.dev.yaml \
  -n vidya-system --create-namespace
```

The `values.dev.yaml` overlay:

- Enables in-cluster PostgreSQL, Redis, and MinIO StatefulSets.
- Disables HPA, KEDA, NetworkPolicy, and off-peak CronJobs.
- Uses `nip.io` wildcard DNS so no `/etc/hosts` edit is needed.
- TLS is disabled; HTTP only.

### 5. Verify

```bash
kubectl get pods -n vidya-system
kubectl get ingress -n vidya-system
# Open http://vidya.127.0.0.1.nip.io in a browser
```

For a fully automated smoke-test, run:

```bash
bash infra/helm/kind-smoke-test.sh
```

---

## Helm Install

### Local dev

```bash
helm install vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.dev.yaml \
  -n vidya-system --create-namespace
```

### Staging

```bash
helm install vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.staging.yaml \
  -n vidya-system --create-namespace
```

### Production

```bash
helm install vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.prod.yaml \
  -n vidya-system --create-namespace
```

### Release name

The release **must** be named `vidya`. The chart's ConfigMap uses the release
name to build service hostnames (e.g. `vidya-redis`, `vidya-postgres`). Using
any other release name breaks internal service discovery.

---

## Helm Upgrade

Pull the latest chart changes, then upgrade in place:

```bash
helm upgrade vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.prod.yaml \
  -n vidya-system
```

The `migrate` pre-upgrade hook runs `alembic upgrade head` automatically before
any pods are replaced. If the migration fails, the upgrade is aborted and the
existing release remains unchanged.

To preview what the upgrade will change without applying it:

```bash
helm diff upgrade vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.prod.yaml \
  -n vidya-system
```

(Requires the `helm-diff` plugin: `helm plugin install https://github.com/databus23/helm-diff`)

---

## Rollback

### List revisions

```bash
helm history vidya -n vidya-system
```

### Roll back to the previous revision

```bash
helm rollback vidya -n vidya-system
```

### Roll back to a specific revision

```bash
helm rollback vidya <REVISION> -n vidya-system
```

A rollback re-runs the `migrate` pre-upgrade hook with the previous image. If
the migration contains destructive DDL (column drops, table renames), the
rollback hook may fail. Test rollback on staging before every production
release that contains schema changes.

### Emergency: roll back pods only (skip migration hook)

```bash
# Not recommended — only if the migration hook itself is broken
helm rollback vidya <REVISION> -n vidya-system --no-hooks
```

---

## Three Deployment Paths

| Feature                | Local dev (kind)     | Staging (self-hosted) | Production (managed cloud) |
|------------------------|----------------------|-----------------------|---------------------------|
| `postgres.enabled`     | `true`               | `false`               | `false`                   |
| `redis.enabled`        | `true`               | `false`               | `false`                   |
| `minio.enabled`        | `true`               | `true`                | `true`                    |
| `externalSecrets`      | `false`              | `true`                | `true`                    |
| `ingress.tls`          | `false`              | `true` (staging cert) | `true` (prod cert)        |
| `certManager.clusterIssuer` | `selfsigned-issuer` | `letsencrypt-staging` | `letsencrypt-prod`   |
| HPA / KEDA             | disabled             | enabled               | enabled                   |
| NetworkPolicy          | disabled             | enabled               | enabled                   |
| Off-peak CronJobs      | disabled             | enabled               | enabled                   |
| `env.ENVIRONMENT`      | `development`        | `staging`             | `production`              |

---

## Secrets Management

### Local dev

Secrets are passed as plain values in `values.dev.yaml` (or a gitignored
`values.dev.secret.yaml`). They are written into a Kubernetes Secret by the
chart when `externalSecrets.enabled: false`.

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit the file that contains real secret values. The recommended pattern:

```bash
cp infra/helm/vidya/values.dev.yaml infra/helm/vidya/values.dev.secret.yaml
echo "infra/helm/vidya/values.dev.secret.yaml" >> .gitignore
# Edit values.dev.secret.yaml with real local values
helm install vidya ./infra/helm/vidya \
  -f infra/helm/vidya/values.dev.yaml \
  -f infra/helm/vidya/values.dev.secret.yaml \
  -n vidya-system --create-namespace
```

### Staging and production

Secrets are managed by the External Secrets Operator. The chart renders
`ExternalSecret` resources (one per logical secret) when
`externalSecrets.enabled: true`. ESO syncs the values from the configured
backend into native Kubernetes Secrets that the pods consume via `envFrom`.

The `secrets:` block in `values.staging.yaml` and `values.prod.yaml` is
intentionally empty (`secrets: {}`). Do not add real values there.

---

## Production Readiness Checklist

Run through this list before every production release.

### Infrastructure

- [ ] `postgres.enabled: false` — in-cluster PG disabled; managed DB in use
- [ ] `redis.enabled: false` — in-cluster Redis disabled; managed Redis in use
- [ ] `externalSecrets.enabled: true` — ESO SecretStore is `Ready`
- [ ] `ingress.tls: true` — HTTPS enforced
- [ ] `certManager.clusterIssuer: letsencrypt-prod` — prod cert issuer
- [ ] `ingress.host` is the real domain (not `CHANGE_ME` or `nip.io`)
- [ ] `pgbouncer.postgresHost` is the real managed DB endpoint
- [ ] `keda.redisAddress` is the real managed Redis endpoint
- [ ] `global.imageRegistry` is set; no bare `vidya/api` image names
- [ ] Image tags are pinned (not `:latest`)

### Scaling and availability

- [ ] `api.hpa.enabled: true` and `api.pdb.enabled: true`
- [ ] `worker.keda.enabled: true` and `worker.pdb.enabled: true`
- [ ] `workerHeavy.keda.enabled: true` and `workerHeavy.pdb.enabled: true`
- [ ] `frontend.hpa.enabled: true` and `frontend.pdb.enabled: true`
- [ ] `offPeak.enabled: true` and timezone/cron times reviewed
- [ ] `networkPolicy.enabled: true`

### Security

- [ ] No real secrets in any committed values file
- [ ] ESO `refreshInterval` is set (`30m` recommended for prod)
- [ ] `env.ENVIRONMENT: production`
- [ ] `env.ACCESS_TOKEN_EXPIRE_MINUTES` is `≤ 30`
- [ ] `migrate.runTenantMigration` is `true` — forward-migrates every tenant schema to head on deploy

### Operations

- [ ] Rollback tested on staging with the exact migration in this release
- [ ] `helm diff upgrade` reviewed and approved by Srinivas
- [ ] Monitoring alerts (Grafana / PagerDuty) verified for the new release
- [ ] `helm history` shows clean revision chain with no failed releases
