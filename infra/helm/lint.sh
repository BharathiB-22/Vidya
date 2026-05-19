#!/usr/bin/env bash
# =============================================================================
# lint.sh  —  Helm lint + template validation for all three environment overlays
# =============================================================================
# Requirements:
#   helm >= 3.12  on PATH
#
# Usage:
#   bash infra/helm/lint.sh
#
# Exit codes:
#   0  all checks passed
#   1  any lint, template, or :latest check failed
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CHART="$REPO_ROOT/infra/helm/vidya"
RELEASE="vidya"
NAMESPACE="vidya-system"

log()  { echo "[lint] $*"; }
fail() { echo "[lint] FAIL: $*" >&2; exit 1; }

command -v helm >/dev/null 2>&1 || fail "helm not found on PATH — install helm >= 3.12"

# ── 1. helm lint ─────────────────────────────────────────────────────────────
for overlay in dev staging prod; do
  log "helm lint (${overlay}) ..."
  helm lint "$CHART" \
    -f "$CHART/values.${overlay}.yaml" \
    --strict \
    --namespace "$NAMESPACE"
done

# ── 2. helm template (dry-run render) ────────────────────────────────────────
for overlay in dev staging prod; do
  log "helm template (${overlay}) ..."
  helm template "$RELEASE" "$CHART" \
    -f "$CHART/values.${overlay}.yaml" \
    --namespace "$NAMESPACE" \
    > /dev/null
done

# ── 3. :latest tag check — prod must never contain :latest ───────────────────
log "Checking prod overlay for :latest image tags ..."
PROD_RENDERED=$(helm template "$RELEASE" "$CHART" \
  -f "$CHART/values.prod.yaml" \
  --namespace "$NAMESPACE")

if echo "$PROD_RENDERED" | grep -E "^\s+image: .*:latest"; then
  fail "prod overlay contains :latest image tag(s) — pin all application tags before deploying to production"
fi
log ":latest check: PASS"

# ── 4. Summary ────────────────────────────────────────────────────────────────
log ""
log "============================================================"
log "All helm lint and template checks passed (dev / staging / prod)"
log "============================================================"
