#!/usr/bin/env bash
# =============================================================================
# lint.sh  —  Helm chart validation gate for all Vidya deployment paths
# =============================================================================
# Runs helm lint and security checks across every values file combination.
# Called by CI (H05-08) before every staging / prod deploy.
#
# USAGE
#   bash infra/helm/vidya/lint.sh                  # full checks (expected to
#                                                  # fail on CHANGE_ME until
#                                                  # H05-04 is complete)
#   bash infra/helm/vidya/lint.sh --skip-change-me # skip CHANGE_ME / :latest
#                                                  # checks (dev / pre-H05-04)
#
# EXIT CODES
#   0  All enabled checks passed
#   1  One or more checks failed (details printed to stdout)
#
# CURRENT EXPECTED BEHAVIOUR (before H05-04)
# ───────────────────────────────────────────
# helm lint steps:  PASS for all paths
# CHANGE_ME check:  FAIL for staging and prod (known; tracked as H05-04)
# :latest check:    PASS (values.prod / staging already pin image tags)
# =============================================================================
set -euo pipefail

CHART_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART="$CHART_DIR"

SKIP_CHANGE_ME=false
for arg in "$@"; do
  case "$arg" in
    --skip-change-me) SKIP_CHANGE_ME=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

ERRORS=0
WARNINGS=0

pass()  { echo "  [PASS] $*"; }
fail()  { echo "  [FAIL] $*"; ERRORS=$((ERRORS + 1)); }
warn()  { echo "  [WARN] $*"; WARNINGS=$((WARNINGS + 1)); }
header(){ echo; echo "── $* ──────────────────────────────────────────────"; }

# ── 1. helm lint — all deployment paths ──────────────────────────────────────
header "helm lint"

lint_path() {
  local label="$1"; shift
  local extra_flags=("$@")
  if helm lint "$CHART" "${extra_flags[@]}" --quiet 2>&1; then
    pass "helm lint [$label]"
  else
    fail "helm lint [$label]"
    # Re-run without --quiet so the error is visible
    helm lint "$CHART" "${extra_flags[@]}" || true
  fi
}

lint_path "base (values.yaml only)"
lint_path "dev"          -f "$CHART/values.dev.yaml"
lint_path "staging"      -f "$CHART/values.staging.yaml"
lint_path "prod"         -f "$CHART/values.prod.yaml"
lint_path "selfhosted"   -f "$CHART/values.selfhosted.yaml"

# ── 2. Rendered output checks — staging and prod only ────────────────────────
header "rendered-output checks (staging + prod)"

check_render() {
  local label="$1"
  local values_file="$2"

  local rendered
  rendered=$(helm template vidya "$CHART" -f "$values_file" 2>/dev/null)

  # 2a. CHANGE_ME strings ────────────────────────────────────────────────────
  if [ "$SKIP_CHANGE_ME" = true ]; then
    warn "[$label] CHANGE_ME check skipped (--skip-change-me)"
  else
    local change_me_count
    change_me_count=$(echo "$rendered" | grep -c "CHANGE_ME" || true)
    if [ "$change_me_count" -gt 0 ]; then
      fail "[$label] $change_me_count CHANGE_ME string(s) found in rendered output"
      echo "       Occurrences:"
      echo "$rendered" | grep -n "CHANGE_ME" | head -20 | sed 's/^/         /'
    else
      pass "[$label] no CHANGE_ME strings"
    fi
  fi

  # 2b. :latest image tags ───────────────────────────────────────────────────
  local latest_count
  latest_count=$(echo "$rendered" | grep -cE 'image:.*:latest' || true)
  if [ "$latest_count" -gt 0 ]; then
    fail "[$label] $latest_count :latest image tag(s) found — pin tags before deploying"
    echo "$rendered" | grep -nE 'image:.*:latest' | head -10 | sed 's/^/         /'
  else
    pass "[$label] no :latest image tags"
  fi

  # 2c. Empty image registry guard ───────────────────────────────────────────
  # Warn (not fail) if imageRegistry is still blank on non-dev paths.
  local empty_registry
  empty_registry=$(echo "$rendered" | grep -cE 'image: [^/]+:[^/]+$' || true)
  if [ "$empty_registry" -gt 0 ] && [ "$SKIP_CHANGE_ME" = false ]; then
    warn "[$label] $empty_registry image(s) have no registry prefix — set global.imageRegistry"
  fi
}

check_render "staging"    "$CHART/values.staging.yaml"
check_render "prod"       "$CHART/values.prod.yaml"
check_render "selfhosted" "$CHART/values.selfhosted.yaml"

# ── 3. values.dev.yaml safety checks ─────────────────────────────────────────
header "dev values safety"

# values.dev.yaml must never have externalSecrets.enabled: true
if grep -q "externalSecrets:" "$CHART/values.dev.yaml"; then
  if grep -A2 "externalSecrets:" "$CHART/values.dev.yaml" | grep -q "enabled: true"; then
    fail "[dev] externalSecrets.enabled: true in values.dev.yaml — must be false for local dev"
  else
    pass "[dev] externalSecrets.enabled: false (correct)"
  fi
fi

# values.dev.yaml must never have tls: true
if grep -q "tls: true" "$CHART/values.dev.yaml"; then
  fail "[dev] tls: true found in values.dev.yaml — local dev must use tls: false"
else
  pass "[dev] tls: false (correct for local dev)"
fi

# ── 4. Summary ────────────────────────────────────────────────────────────────
header "summary"
echo "  Errors:   $ERRORS"
echo "  Warnings: $WARNINGS"

if [ "$ERRORS" -gt 0 ]; then
  echo
  if [ "$SKIP_CHANGE_ME" = false ] && echo "$*" | grep -v "skip" > /dev/null 2>&1; then
    echo "  NOTE: CHANGE_ME failures are expected before H05-04 completes."
    echo "  Run with --skip-change-me to verify only helm lint and :latest checks."
  fi
  echo
  echo "RESULT: FAIL ($ERRORS error(s))"
  exit 1
else
  echo
  echo "RESULT: PASS"
fi
