#!/usr/bin/env bash
#
# deploy.sh — Unified deployment + cleanup for Bank of Anthos (base) + Save2Win
#
# Modes:
#   kubectl  | skaffold  | clean  | nuke  | reset
#
# Flags:
#   --verbose/-v, --dry-run, --yes/-y, --namespace/-n, --mode/-m, --ba-dir
#
set -Eeuo pipefail

# ---------- pretty logging ----------
RED=$'\033[1;31m'; GRN=$'\033[1;32m'; YLW=$'\033[1;33m'; BLU=$'\033[1;34m'; RST=$'\033[0m'
section(){ echo -e "\n${BLU}$*${RST}"; }
info(){ echo -e "  • $*"; }
warn(){ echo -e "${YLW}  ! $*${RST}"; }
ok(){ echo -e "${GRN}  ✓ $*${RST}"; }
err(){ echo -e "${RED}  ✗ $*${RST}"; }

trap 'err "Failed at line $LINENO: $BASH_COMMAND"; err "Run with --verbose for more detail."; exit 1' ERR

usage() {
  cat <<EOF
Usage: ./deploy.sh [MODE] [flags]

Modes (or use --mode/-m):
  kubectl        Apply prebuilt manifests (fast path; no image build)
  skaffold       Build & deploy via Skaffold (uses Artifact Registry)
  clean          Uninstall app resources (skaffold delete OR kubectl delete -f)
  nuke           Delete & recreate the namespace (refuses to nuke 'default')
  reset          Clean then deploy again (uses DEPLOY_MODE or provided MODE)

Flags:
  --verbose, -v        Verbose bash tracing
  --dry-run            Print commands instead of executing
  --yes, -y            Auto-confirm destructive actions
  --namespace, -n VAL  Override K8S_NAMESPACE
  --mode, -m VAL       Override mode
  --ba-dir VAL         Override BA_DIR
EOF
}

run() { if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "+ $*"; else eval "$@"; fi; }
need() { command -v "$1" >/dev/null 2>&1 || { err "Missing required tool: $1"; exit 1; }; }

# ---------- args ----------
MODE_ARG=""; DRY_RUN=0; VERBOSE=0; ASSUME_YES=0; OVERRIDE_NS=""; OVERRIDE_BA_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0;;
    -v|--verbose) VERBOSE=1; shift;;
    --dry-run) DRY_RUN=1; shift;;
    -y|--yes) ASSUME_YES=1; shift;;
    -n|--namespace) OVERRIDE_NS="$2"; shift 2;;
    --ba-dir) OVERRIDE_BA_DIR="$2"; shift 2;;
    -m|--mode) MODE_ARG="$2"; shift 2;;
    kubectl|skaffold|clean|nuke|reset) MODE_ARG="$1"; shift;;
    *) warn "Ignoring unknown arg: $1"; shift;;
  esac
done
[[ $VERBOSE == 1 ]] && set -x

# ---------- load config ----------
[[ -f ".env.local" ]] || { err ".env.local not found. Copy .env.example to .env.local and fill your values."; exit 1; }
# shellcheck disable=SC1091
source ".env.local"

: "${GCP_ACCOUNT_EMAIL:?GCP_ACCOUNT_EMAIL is required in .env.local}"
: "${PROJECT_ID:?PROJECT_ID is required in .env.local}"
: "${CLUSTER_NAME:?CLUSTER_NAME is required in .env.local}"
: "${REGION:?REGION is required in .env.local}"

K8S_NAMESPACE="${OVERRIDE_NS:-${K8S_NAMESPACE:-boa}}"
BA_DIR="${OVERRIDE_BA_DIR:-${BA_DIR:-bank-of-anthos}}"
AR_REPO_NAME="${AR_REPO_NAME:-bank-of-anthos-repo}"
AR_HOSTNAME="${AR_HOSTNAME:-$REGION-docker.pkg.dev}"
SKAFFOLD_DEFAULT_REPO="${SKAFFOLD_DEFAULT_REPO:-$AR_HOSTNAME/$PROJECT_ID/$AR_REPO_NAME}"
DEPLOY_MODE="${DEPLOY_MODE:-kubectl}"

MODE="${MODE_ARG:-$DEPLOY_MODE}"
RESET_MODE="${RESET_MODE:-$DEPLOY_MODE}"

echo -e "\n${BLU}▶ Save2Win / Bank of Anthos — ${MODE^^}${RST}"
info "Project: ${PROJECT_ID} | Region: ${REGION} | Cluster: ${CLUSTER_NAME} | Namespace: ${K8S_NAMESPACE}"
info "BA_DIR: ${BA_DIR}"

# ---------- preflight ----------
need gcloud; need kubectl
if [[ "$MODE" == "skaffold" || "$MODE" == "reset" ]]; then
  if [[ "$MODE" == "skaffold" || "$RESET_MODE" == "skaffold" ]]; then need skaffold; fi
fi

section "[1/7] Authenticate & set project"
# Single call sets user creds AND ADC using device flow (no browser launch)
# NOTE: --no-browser (not --no-launch-browser) for device code flow, and --update-adc to write ADC file.
run gcloud auth login "$GCP_ACCOUNT_EMAIL" --no-browser --update-adc
run gcloud config set project "$PROJECT_ID"
ok "User creds set for: $GCP_ACCOUNT_EMAIL"

# Verify ADC exists; fallback to explicit ADC login if needed
ADC_FILE="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"
if [[ ! -s "$ADC_FILE" ]]; then
  warn "ADC file not found at: $ADC_FILE — trying 'gcloud auth application-default login --no-browser'..."
  run gcloud auth application-default login --no-browser
  ADC_FILE="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"
fi
[[ -s "$ADC_FILE" ]] && ok "ADC ready at: $ADC_FILE" || { err "ADC still missing. See 'Manual fix' notes at end."; exit 1; }

# Quick token check
run gcloud auth list
run gcloud auth application-default print-access-token >/dev/null && ok "ADC token OK"

section "[2/7] Enable required Cloud APIs"
run gcloud services enable container.googleapis.com --project "$PROJECT_ID"

ensure_ar() {
  run gcloud services enable artifactregistry.googleapis.com cloudbuild.googleapis.com --project "$PROJECT_ID"
  if ! gcloud artifacts repositories describe "$AR_REPO_NAME" --location="$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
    info "Creating Artifact Registry repo: $AR_REPO_NAME"
    run gcloud artifacts repositories create "$AR_REPO_NAME" \
      --repository-format=docker \
      --location="$REGION" \
      --project "$PROJECT_ID"
  else
    ok "Artifact Registry repo exists."
  fi
  run gcloud auth configure-docker "$AR_HOSTNAME" --project "$PROJECT_ID"
  export SKAFFOLD_DEFAULT_REPO
  ok "SKAFFOLD_DEFAULT_REPO=$SKAFFOLD_DEFAULT_REPO"
}

if [[ "$MODE" == "skaffold" || ("$MODE" == "reset" && "$RESET_MODE" == "skaffold") ]]; then
  ensure_ar
fi

section "[3/7] Configure kubectl context"
run gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION" --project "$PROJECT_ID"
KUBE_CONTEXT="$(kubectl config current-context)"
ok "Using kube-context: $KUBE_CONTEXT"
run "kubectl get ns \"$K8S_NAMESPACE\" >/dev/null 2>&1 || kubectl create namespace \"$K8S_NAMESPACE\""

# ---------- helpers ----------
find_manifest_dir() {
  if [[ -d "$BA_DIR/kubernetes-manifests" ]]; then echo "$BA_DIR/kubernetes-manifests"
  elif [[ -d "kubernetes-manifests" ]]; then echo "kubernetes-manifests"
  else err "Could not find kubernetes-manifests directory."; return 1; fi
}
apply_jwt_secret() {
  if [[ -f "$BA_DIR/extras/jwt/jwt-secret.yaml" ]]; then run kubectl apply -n "$K8S_NAMESPACE" -f "$BA_DIR/extras/jwt/jwt-secret.yaml"
  elif [[ -f "extras/jwt/jwt-secret.yaml" ]]; then run kubectl apply -n "$K8S_NAMESPACE" -f "extras/jwt/jwt-secret.yaml"
  else warn "JWT secret file not found (skipping)."; fi
}
deploy_kubectl() {
  section "[4/7] Deploy via kubectl apply (prebuilt images)"
  apply_jwt_secret
  local md; md="$(find_manifest_dir)"; info "Applying manifests from: $md"
  run kubectl apply -n "$K8S_NAMESPACE" -f "$md/"
}
wait_rollouts() {
  section "[5/7] Waiting for deployments to be available"
  set +e; local DEPLOYS; DEPLOYS=$(kubectl get deploy -n "$K8S_NAMESPACE" -o name 2>/dev/null); set -e
  if [[ -n "$DEPLOYS" ]]; then
    while IFS= read -r d; do info "rollout: $(basename "$d")"; run kubectl rollout status -n "$K8S_NAMESPACE" "$d" --timeout=240s || true; done <<< "$DEPLOYS"
  else warn "No deployments found (manifests may use other controllers)."; fi
}
deploy_skaffold() {
  section "[4/7] Deploy via Skaffold (build + deploy)"
  [[ -d "$BA_DIR" ]] || { err "BA_DIR '$BA_DIR' not found."; exit 1; }
  [[ -f "$BA_DIR/skaffold.yaml" ]] || { err "$BA_DIR/skaffold.yaml not found."; exit 1; }
  local USE_PROFILE=""; if ! docker info >/dev/null 2>&1; then USE_PROFILE="-p gcb"; warn "Docker not detected. Will try Cloud Build profile 'gcb' (if defined)."; fi
  set +e
  ( cd "$BA_DIR"; echo "Running: skaffold run $USE_PROFILE -m bank-of-anthos --kube-context=\"$KUBE_CONTEXT\" --status-check --tail"; skaffold run $USE_PROFILE -m bank-of-anthos --kube-context="$KUBE_CONTEXT" --status-check --tail )
  local RC=$?; set -e
  if [[ $RC -ne 0 ]]; then warn "Module attempt failed. Retrying without -m..."; ( cd "$BA_DIR"; echo "Running: skaffold run $USE_PROFILE --kube-context=\"$KUBE_CONTEXT\" --status-check --tail"; skaffold run $USE_PROFILE --kube-context="$KUBE_CONTEXT" --status-check --tail ); fi
}
diagnose_if_stuck() {
  section "[Diag] Checking pod statuses (common 'stuck' reasons)"
  kubectl get pods -n "$K8S_NAMESPACE" -o wide || true
  local BAD; BAD=$(kubectl get pods -n "$K8S_NAMESPACE" --no-headers 2>/dev/null | grep -E "ImagePullBackOff|ErrImagePull|CrashLoopBackOff|Error|Pending" || true)
  if [[ -n "$BAD" ]]; then
    warn "Detected non-ready pods:"; echo "$BAD"
    local firstBad; firstBad=$(echo "$BAD" | awk '{print $1}' | head -n1)
    warn "Describing pod: $firstBad"; kubectl describe pod -n "$K8S_NAMESPACE" "$firstBad" | sed -n '1,120p' || true
    warn "Recent logs from first container in $firstBad:"
    local firstC; firstC=$(kubectl get pod -n "$K8S_NAMESPACE" "$firstBad" -o jsonpath='{.spec.containers[0].name}' 2>/dev/null || echo "")
    if [[ -n "$firstC" ]]; then kubectl logs -n "$K8S_NAMESPACE" "$firstBad" -c "$firstC" --tail=120 || true; fi
    warn "Hints:"; echo "  - ImagePullBackOff → wrong image/tag or registry auth missing."; echo "  - Pending → node quotas or Autopilot constraints; see events above."; echo "  - CrashLoopBackOff → app failing; see logs above."
  else ok "No obvious pod errors."; fi
}
wait_external_ip() {
  section "[6/7] Waiting for External IP (frontend or frontend-external)"
  local tries=30 sleepsec=10
  for ((i=1; i<=tries; i++)); do
    local ip; ip=$(kubectl get svc -n "$K8S_NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.loadBalancer.ingress[0].ip}{"\n"}{end}' | grep -E '^frontend(-external)?\s' | awk '{print $2}' || true)
    if [[ -n "$ip" ]]; then ok "Service is reachable at: http://$ip"; echo "Open in browser: http://$ip"; return 0; fi
    info "Attempt $i/$tries: External IP not ready yet..."; sleep "$sleepsec"
  done
  warn "External IP still pending. Check again with: kubectl get svc -n \"$K8S_NAMESPACE\" | grep frontend"
}
post_info() {
  section "[7/7] Post-checks"
  kubectl get pods -n "$K8S_NAMESPACE" | sed -n '1,30p' || true; echo; kubectl get svc -n "$K8S_NAMESPACE" | sed -n '1,30p' || true
}

confirm() { [[ "${ASSUME_YES:-0}" == "1" ]] && return 0; read -r -p "Proceed? (y/N) " ans; [[ "$ans" =~ ^[Yy]$ ]]; }
clean_kubectl() {
  section "[Cleanup] kubectl delete -f manifests"
  local md; md="$(find_manifest_dir)"; run kubectl delete -n "$K8S_NAMESPACE" -f "$md/" --ignore-not-found=true || true
  if kubectl get secret -n "$K8S_NAMESPACE" jwt-secret >/dev/null 2>&1; then run kubectl delete secret jwt-secret -n "$K8S_NAMESPACE" || true; fi
}
clean_skaffold() {
  section "[Cleanup] skaffold delete"
  ( cd "$BA_DIR"; set +e; skaffold delete -m bank-of-anthos --kube-context="$KUBE_CONTEXT"; local RC=$?; set -e; if [[ $RC -ne 0 ]]; then skaffold delete --kube-context="$KUBE_CONTEXT" || true; fi )
}
nuke_namespace() {
  [[ "$K8S_NAMESPACE" == "default" ]] && { err "Refusing to nuke 'default' namespace."; exit 1; }
  section "[NUKE] Delete & recreate namespace '$K8S_NAMESPACE'"
  info "This will delete ALL resources in namespace '$K8S_NAMESPACE'."; confirm || { warn "Cancelled."; exit 0; }
  run kubectl delete ns "$K8S_NAMESPACE" --ignore-not-found=true || true; run kubectl create ns "$K8S_NAMESPACE"; ok "Namespace recreated."
}

# ---------- orchestrate ----------
case "${MODE}" in
  kubectl)  deploy_kubectl; wait_rollouts; diagnose_if_stuck; wait_external_ip; post_info ;;
  skaffold) deploy_skaffold; diagnose_if_stuck; wait_external_ip; post_info ;;
  clean)    if [[ -f "$BA_DIR/skaffold.yaml" ]]; then clean_skaffold || clean_kubectl; else clean_kubectl; fi ;;
  nuke)     nuke_namespace ;;
  reset)    if [[ "$RESET_MODE" == "skaffold" ]]; then ensure_ar; clean_skaffold || clean_kubectl; deploy_skaffold; else clean_kubectl || clean_skaffold; deploy_kubectl; wait_rollouts; fi; diagnose_if_stuck; wait_external_ip; post_info ;;
  *) usage; exit 1 ;;
esac

# Manual fix notes (only displayed on ADC failure):
# 1) Check Cloud SDK version: gcloud --version
# 2) Remove stale ADC then retry: rm -f "${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}/application_default_credentials.json"
# 3) Run: gcloud auth login --no-browser --update-adc
# 4) Verify: gcloud auth application-default print-access-token
