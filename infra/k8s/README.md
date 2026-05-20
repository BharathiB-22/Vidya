# infra/k8s — Cluster-Level Manifests

This directory holds Kubernetes manifests that are applied to the cluster
**before** `helm install` runs. These are cluster-level prerequisites that
the Helm chart itself does not manage.

## Apply order

```
1. Install ESO, cert-manager, KEDA, ingress-nginx (via their own Helm charts)
2. kubectl apply -f infra/k8s/secret-store-vault.yaml    ← ClusterSecretStore
3. kubectl get clustersecretstore vidya-secret-store      ← must be Ready
4. helm upgrade --install vidya ./infra/helm/vidya ...
```

## Files in this directory

| File | Purpose | Apply when |
|------|---------|-----------|
| `secret-store-vault.yaml.example` | Vault ClusterSecretStore template — copy to `secret-store-vault.yaml`, fill in Vault address and role, apply | Before staging / prod `helm install` |

## Gitignore rules

Files matching `*.secret.yaml` are gitignored (see root `.gitignore`).
Manifests with real credentials (tokens, certs) must use the `.secret.yaml`
suffix so they are never committed.

Use the `.example` files as templates:
```
cp infra/k8s/secret-store-vault.yaml.example infra/k8s/secret-store-vault.yaml
# edit the copy with real values
kubectl apply -f infra/k8s/secret-store-vault.yaml -n vidya-system
```
