#!/usr/bin/env bash
# =============================================================================
# kind-smoke-test.sh  —  Create a kind cluster and smoke-test Vidya locally
# =============================================================================
# Usage:
#   bash infra/helm/kind-smoke-test.sh [--skip-cluster] [--skip-prereqs]
#
# Flags:
#   --skip-cluster   Skip "kind create cluster" (use existing vidya-dev cluster)
#   --skip-prereqs   Skip Helm repo adds and prerequisite chart installs
#
# Requirements:
#   kind, kubectl, helm  installed and on PATH
#   Docker running
#
# The script exits immediately on any error (set -euo pipefail).
# =============================================================================
set -euo pipefail

CLUSTER_NAME="vidya-dev"
NAMESPACE="vidya-system"
CHART_DIR="$(cd "$(dirname "$0")/../helm/vidya" && pwd)"
TIMEOUT=300   # seconds to wait for rollout

SKIP_CLUSTER=false
SKIP_PREREQS=false

for arg in "$@"; do
  case "$arg" in
    --skip-cluster)  SKIP_CLUSTER=true  ;;
    --skip-prereqs)  SKIP_PREREQS=true  ;;
  esac
done

# ── helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[smoke] $*"; }
die()  { echo "[smoke] ERROR: $*" >&2; exit 1; }
wait_deploy() {
  local name=$1
  log "Waiting for deployment/$name in $NAMESPACE ..."
  kubectl rollout status deployment/"$name" -n "$NAMESPACE" --timeout="${TIMEOUT}s"
}

# ── 1. Create kind cluster ────────────────────────────────────────────────────
if [ "$SKIP_CLUSTER" = false ]; then
  log "Creating kind cluster: $CLUSTER_NAME"
  kind create cluster \
    --config "$(dirname "$0")/kind-config.yaml" \
    --name "$CLUSTER_NAME"
fi

kubectl cluster-info --context "kind-$CLUSTER_NAME" > /dev/null
log "Cluster context: kind-$CLUSTER_NAME"

# ── 2. Install prerequisites ──────────────────────────────────────────────────
if [ "$SKIP_PREREQS" = false ]; then
  log "Adding Helm repos ..."
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx  --force-update
  helm repo add kedacore      https://kedacore.github.io/charts           --force-update
  helm repo update

  log "Installing ingress-nginx ..."
  helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx --create-namespace \
    --set controller.hostPort.enabled=true \
    --set controller.service.type=NodePort \
    --set controller.service.nodePorts.http=30080 \
    --set controller.service.nodePorts.https=30443 \
    --wait --timeout 120s

  log "Installing KEDA ..."
  helm upgrade --install keda kedacore/keda \
    --namespace keda --create-namespace \
    --wait --timeout 120s
fi

# ── 3. Install Vidya chart ────────────────────────────────────────────────────
log "Installing Vidya chart ..."
helm upgrade --install vidya "$CHART_DIR" \
  -f "$CHART_DIR/values.dev.yaml" \
  --namespace "$NAMESPACE" --create-namespace \
  --wait --timeout "${TIMEOUT}s"

# ── 4. Wait for core deployments ─────────────────────────────────────────────
log "Waiting for pods to be ready ..."
wait_deploy vidya-api
wait_deploy vidya-frontend
wait_deploy vidya-worker
wait_deploy vidya-pgbouncer

kubectl rollout status statefulset/vidya-postgres -n "$NAMESPACE" --timeout="${TIMEOUT}s"
kubectl rollout status statefulset/vidya-redis    -n "$NAMESPACE" --timeout="${TIMEOUT}s"
kubectl rollout status statefulset/vidya-minio    -n "$NAMESPACE" --timeout="${TIMEOUT}s"

# ── 5. Health checks ──────────────────────────────────────────────────────────
log "Running health checks ..."

# API liveness probe via in-cluster exec
API_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/component=api \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n "$NAMESPACE" "$API_POD" -- \
  wget -qO- http://localhost:8000/healthz | grep -q '"status"'
log "API /healthz: OK"

# Ingress reachability (nip.io wildcard — no DNS config needed)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  http://vidya.127.0.0.1.nip.io/healthz || true)
if [ "$HTTP_CODE" = "200" ]; then
  log "Ingress http://vidya.127.0.0.1.nip.io/healthz: OK (200)"
else
  log "WARN: Ingress returned HTTP $HTTP_CODE (expected 200). Check ingress-nginx logs."
fi

# ── 6. Summary ────────────────────────────────────────────────────────────────
log ""
log "============================================================"
log "Vidya smoke test PASSED"
log "  API:      http://vidya.127.0.0.1.nip.io/api"
log "  Frontend: http://vidya.127.0.0.1.nip.io"
log "  Flower:   kubectl port-forward svc/vidya-flower 5555:5555 -n $NAMESPACE"
log "  MinIO:    kubectl port-forward svc/vidya-minio 9000:9000 -n $NAMESPACE"
log ""
log "To tear down:"
log "  kind delete cluster --name $CLUSTER_NAME"
log "============================================================"
