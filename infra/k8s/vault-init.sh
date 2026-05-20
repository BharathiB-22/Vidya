#!/usr/bin/env bash
# =============================================================================
# vault-init.sh  —  Vault initialisation for Vidya (staging + prod)
# =============================================================================
#
# Run this script once per environment before the first `helm install`.
# It configures Vault Kubernetes auth, writes the Vidya read policy, creates
# the role binding, and populates the KV v2 paths for staging and prod.
#
# PREREQUISITES
# -------------
#   1. vault CLI installed and on PATH
#   2. VAULT_ADDR set to your Vault server   (export VAULT_ADDR="https://...")
#   3. VAULT_TOKEN set to a root/admin token (export VAULT_TOKEN="...")
#   4. kubectl configured for the target cluster (used for k8s auth config)
#
# USAGE
#       bash infra/k8s/vault-init.sh [staging|prod|all]
#
#       DRY_RUN=1 bash infra/k8s/vault-init.sh staging   # print commands only
#
# SECRETS — DO NOT PASTE REAL VALUES INTO THIS SCRIPT
# ----------------------------------------------------
# The script prompts for secret values interactively (or reads from env vars
# named VIDYA_<SECRET> for non-interactive CI use).
# Never commit real secrets to this file.
#
# KV PATH LAYOUT
# --------------
#   Mount:    secret  (KV v2)
#   Staging:  secret/data/vidya/staging  (all fields in one KV entry)
#   Prod:     secret/data/vidya/prod
#
# VAULT POLICY
#   vidya-read: path "secret/data/vidya/*" { capabilities = ["read"] }
#
# VAULT ROLE
#   Name:          vidya
#   ServiceAccount: vidya   (matches Helm chart serviceAccount.name)
#   Namespace:     vidya-system
#   Policy:        vidya-read
#   TTL:           1h (renewable; ESO refreshes before expiry)
# =============================================================================
set -euo pipefail

# ── Guards ────────────────────────────────────────────────────────────────────

if [[ -z "${VAULT_ADDR:-}" ]]; then
  echo "ERROR: VAULT_ADDR is not set. Export the Vault server URL first:"
  echo "  export VAULT_ADDR=\"https://vault.your-domain.com\""
  exit 1
fi

if [[ -z "${VAULT_TOKEN:-}" ]]; then
  echo "ERROR: VAULT_TOKEN is not set. Export an admin token first:"
  echo "  export VAULT_TOKEN=\"hvs.XXXX\""
  exit 1
fi

ENV="${1:-all}"
if [[ "$ENV" != "staging" && "$ENV" != "prod" && "$ENV" != "all" ]]; then
  echo "Usage: $0 [staging|prod|all]"
  exit 1
fi

DRY_RUN="${DRY_RUN:-0}"

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

prompt_or_env() {
  local var_name="$1"
  local prompt_text="$2"
  local env_var="VIDYA_${var_name}"
  if [[ -n "${!env_var:-}" ]]; then
    echo "${!env_var}"
  else
    read -rsp "  ${prompt_text}: " val
    echo ""  # newline after silent read
    echo "$val"
  fi
}

header() { echo; echo "── $* ────────────────────────────────────────────"; }

# ── Section 1: KV v2 mount ────────────────────────────────────────────────────
header "1/7  KV v2 mount"

echo "Enabling KV v2 at mount 'secret' (idempotent — ok if already enabled)..."
run vault secrets enable -path=secret kv-v2 2>/dev/null || \
  echo "  [OK] secret/ already enabled"

# ── Section 2: Kubernetes auth ────────────────────────────────────────────────
header "2/7  Kubernetes auth"

echo "Enabling Kubernetes auth method (idempotent)..."
run vault auth enable kubernetes 2>/dev/null || \
  echo "  [OK] kubernetes auth already enabled"

echo "Configuring Kubernetes auth (reads cluster API from current kubeconfig)..."
K8S_HOST=$(kubectl config view --raw -o jsonpath='{.clusters[0].cluster.server}')
K8S_CA=$(kubectl get configmap kube-root-ca.crt -n kube-system \
  -o jsonpath='{.data.ca\.crt}' | base64 | tr -d '\n')

run vault write auth/kubernetes/config \
  kubernetes_host="${K8S_HOST}" \
  kubernetes_ca_cert="$(echo "${K8S_CA}" | base64 -d)"

# ── Section 3: Policy ─────────────────────────────────────────────────────────
header "3/7  Vault policy (vidya-read)"

echo "Writing vidya-read policy..."
if [[ "$DRY_RUN" == "1" ]]; then
  echo "[DRY-RUN] vault policy write vidya-read <HCL>"
else
  vault policy write vidya-read - <<'POLICY'
path "secret/data/vidya/*" {
  capabilities = ["read"]
}
path "secret/metadata/vidya/*" {
  capabilities = ["read", "list"]
}
POLICY
fi
echo "  [OK] policy vidya-read written"

# ── Section 4: Vault role ─────────────────────────────────────────────────────
header "4/7  Vault role binding"

echo "Creating role 'vidya' bound to SA vidya in namespace vidya-system..."
run vault write auth/kubernetes/role/vidya \
  bound_service_account_names=vidya \
  bound_service_account_namespaces=vidya-system \
  policies=vidya-read \
  ttl=1h

echo "  [OK] role vidya created"

# ── Section 5: Populate STAGING secrets ──────────────────────────────────────
populate_env() {
  local env_label="$1"   # "staging" or "prod"
  local kv_path="secret/vidya/${env_label}"

  header "Populating ${env_label} secrets at ${kv_path}"
  echo "Enter values for ${env_label}. Press Enter to leave blank (stores empty string)."
  echo "To use env vars instead of prompts, prefix with VIDYA_ e.g. VIDYA_DATABASE_URL=..."
  echo ""

  local DB_URL; DB_URL=$(prompt_or_env "DATABASE_URL" "DATABASE_URL (postgresql+asyncpg://...)")
  local PG_PASS; PG_PASS=$(prompt_or_env "POSTGRES_PASSWORD" "POSTGRES_PASSWORD")
  local REDIS_URL; REDIS_URL=$(prompt_or_env "REDIS_URL" "REDIS_URL (redis://:pass@host:6379/0)")
  local REDIS_PASS; REDIS_PASS=$(prompt_or_env "REDIS_PASSWORD" "REDIS_PASSWORD")
  local JWT; JWT=$(prompt_or_env "JWT_SECRET" "JWT_SECRET (min 64 hex chars — openssl rand -hex 32)")
  local FERNET; FERNET=$(prompt_or_env "EXAM_FERNET_KEY" "EXAM_FERNET_KEY (python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')")
  local S3_KEY; S3_KEY=$(prompt_or_env "S3_ACCESS_KEY" "S3_ACCESS_KEY (MinIO root user)")
  local S3_SEC; S3_SEC=$(prompt_or_env "S3_SECRET_KEY" "S3_SECRET_KEY (MinIO root password)")
  local GEMINI; GEMINI=$(prompt_or_env "GEMINI_API_KEY" "GEMINI_API_KEY")
  local GROQ; GROQ=$(prompt_or_env "GROQ_API_KEY" "GROQ_API_KEY")
  local SMTP; SMTP=$(prompt_or_env "SMTP_PASSWORD" "SMTP_PASSWORD (leave blank to disable email)")
  local FL_USER; FL_USER=$(prompt_or_env "FLOWER_USER" "FLOWER_USER (default: admin)")
  FL_USER="${FL_USER:-admin}"
  local FL_PASS; FL_PASS=$(prompt_or_env "FLOWER_PASSWORD" "FLOWER_PASSWORD")
  local YT; YT=$(prompt_or_env "YOUTUBE_API_KEY" "YOUTUBE_API_KEY (leave blank if not using YouTube adapter)")

  run vault kv put "${kv_path}" \
    DATABASE_URL="${DB_URL}" \
    POSTGRES_PASSWORD="${PG_PASS}" \
    REDIS_URL="${REDIS_URL}" \
    REDIS_PASSWORD="${REDIS_PASS}" \
    JWT_SECRET="${JWT}" \
    EXAM_FERNET_KEY="${FERNET}" \
    S3_ACCESS_KEY="${S3_KEY}" \
    S3_SECRET_KEY="${S3_SEC}" \
    GEMINI_API_KEY="${GEMINI}" \
    GROQ_API_KEY="${GROQ}" \
    SMTP_PASSWORD="${SMTP}" \
    FLOWER_USER="${FL_USER}" \
    FLOWER_PASSWORD="${FL_PASS}" \
    YOUTUBE_API_KEY="${YT}"

  echo "  [OK] ${env_label} secrets written to ${kv_path}"
}

if [[ "$ENV" == "staging" || "$ENV" == "all" ]]; then
  populate_env "staging"
fi

if [[ "$ENV" == "prod" || "$ENV" == "all" ]]; then
  populate_env "prod"
fi

# ── Section 6: GHCR image pull secret ────────────────────────────────────────
header "6/7  GHCR image pull secret"

echo "Creating ghcr.io pull secret in vidya-system namespace..."
echo "You need a GitHub Personal Access Token (classic) with 'read:packages' scope."
echo "Create one at: https://github.com/settings/tokens"
echo ""

GHCR_USER="${VIDYA_GHCR_USER:-BharathiB-22}"
GHCR_TOKEN="${VIDYA_GHCR_TOKEN:-}"
if [[ -z "$GHCR_TOKEN" ]]; then
  read -rsp "  GitHub PAT (read:packages scope): " GHCR_TOKEN
  echo ""
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "[DRY-RUN] kubectl create secret docker-registry ghcr-pull-secret \\"
  echo "  --docker-server=ghcr.io --docker-username=${GHCR_USER} \\"
  echo "  --docker-password=<token> -n vidya-system"
else
  kubectl create secret docker-registry ghcr-pull-secret \
    --docker-server=ghcr.io \
    --docker-username="${GHCR_USER}" \
    --docker-password="${GHCR_TOKEN}" \
    -n vidya-system \
    --dry-run=client -o yaml | kubectl apply -f -
fi

echo ""
echo "  Add to values.prod.yaml (or values.staging.yaml):"
echo "    global:"
echo "      imagePullSecrets:"
echo "        - name: ghcr-pull-secret"

# ── Section 7: Verify ─────────────────────────────────────────────────────────
header "7/7  Verify"

if [[ "$DRY_RUN" != "1" ]]; then
  echo "Vault KV paths written:"
  if [[ "$ENV" == "staging" || "$ENV" == "all" ]]; then
    echo "  staging:"
    vault kv get -format=table secret/vidya/staging | head -6 || true
  fi
  if [[ "$ENV" == "prod" || "$ENV" == "all" ]]; then
    echo "  prod:"
    vault kv get -format=table secret/vidya/prod | head -6 || true
  fi

  echo ""
  echo "Post-install ESO health check (run after helm install):"
  echo "  kubectl describe externalsecret vidya-secret -n vidya-system"
  echo "  # Look for: Status.Conditions[0].Type=Ready, Reason=SecretSynced"
  echo ""
  echo "  kubectl get secret vidya-secret -n vidya-system -o jsonpath='{.data.JWT_SECRET}' | base64 -d | head -c 8"
  echo "  # Should print the first 8 chars of your JWT_SECRET (verify non-empty)"
fi

echo ""
echo "DONE. Next step: apply the SecretStore, then run helm install."
echo "  kubectl apply -f infra/k8s/secret-store-vault.yaml -n vidya-system"
echo "  helm upgrade --install vidya ./infra/helm/vidya -f values.staging.yaml -n vidya-system"
