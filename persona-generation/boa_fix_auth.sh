#!/usr/bin/env bash
#
# boa-fix-auth.sh (v2) — One-touch fixer for Bank of Anthos auth + wiring on GKE
#
# What this does (idempotent):
#  1) Ensures kubectl context (optionally via gcloud get-credentials)
#  2) Creates/rotates JWT keypair secret `jwt-key` (private+public)
#  3) Aligns routing #: LOCAL_ROUTING_NUM (defaults to 123456789)
#  4) Patches userservice to mount private key + set common envs (pure kubectl)
#  5) Ensures transactionhistory consumes PUB_KEY_PATH + routing
#  6) Fixes frontend HISTORY_API_ADDR (host:port only)
#  7) (Optional) Workload Identity: binds KSA bank-of-anthos → GSA with Cloud Ops roles
#  8) (Optional) Smoke test: calls /healthy and /transactions/<acct> with a dev JWT
#
# Usage:
#   chmod +x boa-fix-auth.sh
#   ./boa-fix-auth.sh --project <PROJECT_ID> --region <REGION> --cluster <CLUSTER_NAME> \
#     [--namespace boa] [--routing 123456789] [--account 3566835414] [--user sf_structures] \
#     [--rotate-jwt] [--no-wi] [--no-smoke]
#
set -Eeuo pipefail

# ---------- Defaults ----------
PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-}"
CLUSTER_NAME="${CLUSTER_NAME:-}"
NAMESPACE="${NAMESPACE:-boa}"
ROUTING="${ROUTING:-123456789}"
ACCOUNT_ID="${ACCOUNT_ID:-3566835414}"
ACCOUNT_USER="${ACCOUNT_USER:-sf_structures}"

USERSERVICE_DEPLOY="${USERSERVICE_DEPLOY:-userservice}"
HISTORY_DEPLOY="${HISTORY_DEPLOY:-transactionhistory}"
FRONTEND_DEPLOY="${FRONTEND_DEPLOY:-frontend}"

JWT_SECRET_NAME="${JWT_SECRET_NAME:-jwt-key}"
PUB_KEY_PATH="${PUB_KEY_PATH:-/tmp/.ssh/publickey}"
PRIV_KEY_PATH="${PRIV_KEY_PATH:-/tmp/.ssh/privatekey}"

APPLY_WI="${APPLY_WI:-true}"          # --no-wi to skip
DO_SMOKE="${DO_SMOKE:-true}"          # --no-smoke to skip
ROTATE_JWT="${ROTATE_JWT:-false}"     # --rotate-jwt to force new keypair

GSA_NAME="${GSA_NAME:-boa-runtime}"
KSA_SHARED="${KSA_SHARED:-bank-of-anthos}"

# ---------- Helpers ----------
bold() { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*"; }
die() { red "ERROR: $*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "Missing required tool: $1"; }

usage() {
  cat <<EOF
$(bold "boa-fix-auth.sh (v2)")
Fixes BoA JWT auth + wiring on GKE Autopilot (idempotent, pure kubectl patches).

Flags:
  --project <id>        GCP project (required unless set in env PROJECT_ID)
  --region <region>     GKE region  (required unless set in env REGION)
  --cluster <name>      GKE cluster (required unless set in env CLUSTER_NAME)
  --namespace <ns>      Kubernetes namespace (default: boa)
  --routing <num>       LOCAL_ROUTING_NUM to use (default: 123456789)
  --account <id>        Account id for smoke test (default: 3566835414)
  --user <name>         Username for smoke test (default: sf_structures)

  --rotate-jwt          Force new RSA keypair + recreate secret ${JWT_SECRET_NAME}
  --no-wi               Skip Workload Identity fix (bank-of-anthos KSA → GSA)
  --no-smoke            Skip curl/transactions smoke test

Env overrides are supported for all variables above.
EOF
}

# ---------- Parse args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2;;
    --region) REGION="$2"; shift 2;;
    --cluster) CLUSTER_NAME="$2"; shift 2;;
    --namespace) NAMESPACE="$2"; shift 2;;
    --routing) ROUTING="$2"; shift 2;;
    --account) ACCOUNT_ID="$2"; shift 2;;
    --user) ACCOUNT_USER="$2"; shift 2;;
    --rotate-jwt) ROTATE_JWT=true; shift;;
    --no-wi) APPLY_WI=false; shift;;
    --no-smoke) DO_SMOKE=false; shift;;
    -h|--help) usage; exit 0;;
    *) die "Unknown flag: $1 (use --help)";;
  esac
done

# ---------- Checks ----------
need kubectl
need openssl
need python3

# If any of the gcloud vars are set, require gcloud
if [[ -n "${PROJECT_ID}" || -n "${REGION}" || -n "${CLUSTER_NAME}" ]]; then
  need gcloud
fi

# ---------- Kube context ----------
if [[ -n "${PROJECT_ID}" && -n "${REGION}" && -n "${CLUSTER_NAME}" ]]; then
  bold "[1/8] Get GKE credentials"
  gcloud container clusters get-credentials "${CLUSTER_NAME}" --region "${REGION}" --project "${PROJECT_ID}"
fi

kubectl get ns "${NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${NAMESPACE}"

# ---------- 2) JWT secret (generate if missing or rotate) ----------
bold "[2/8] Ensure JWT keypair secret: ${JWT_SECRET_NAME}"
set +e
kubectl -n "${NAMESPACE}" get secret "${JWT_SECRET_NAME}" >/dev/null 2>&1
HAS_SECRET=$?
set -e

if [[ "${ROTATE_JWT}" == "true" && "${HAS_SECRET}" -eq 0 ]]; then
  yellow "Rotating JWT secret ${JWT_SECRET_NAME} (deleting then recreating)"
  kubectl -n "${NAMESPACE}" delete secret "${JWT_SECRET_NAME}" --ignore-not-found
  HAS_SECRET=1
fi

if [[ "${HAS_SECRET}" -ne 0 ]]; then
  TMPDIR="$(mktemp -d)"
  openssl genrsa -out "${TMPDIR}/jwtRS256.key" 2048 >/dev/null 2>&1
  openssl rsa -in "${TMPDIR}/jwtRS256.key" -pubout -out "${TMPDIR}/jwtRS256.key.pub" >/dev/null 2>&1
  kubectl -n "${NAMESPACE}" create secret generic "${JWT_SECRET_NAME}" \
    --from-file=jwtRS256.key="${TMPDIR}/jwtRS256.key" \
    --from-file=jwtRS256.key.pub="${TMPDIR}/jwtRS256.key.pub"
  rm -rf "${TMPDIR}"
  green "Created secret ${JWT_SECRET_NAME}"
else
  green "Secret ${JWT_SECRET_NAME} already exists"
fi

# ---------- 3) Align routing + PUB_KEY_PATH in environment-config ----------
bold "[3/8] Patch ConfigMap environment-config"
kubectl -n "${NAMESPACE}" get configmap environment-config >/dev/null 2>&1 || \
  kubectl -n "${NAMESPACE}" create configmap environment-config

kubectl -n "${NAMESPACE}" patch configmap environment-config --type merge -p \
  "{\"data\":{\"LOCAL_ROUTING_NUM\":\"${ROUTING}\",\"PUB_KEY_PATH\":\"${PUB_KEY_PATH}\"}}"

# ---------- 4) Patch userservice to mount private key + set envs (pure kubectl) ----------
bold "[4/8] Patch userservice for private key + envs"

# Ensure Deployment exists
if ! kubectl -n "${NAMESPACE}" get deploy "${USERSERVICE_DEPLOY}" >/dev/null 2>&1; then
  die "Deployment ${USERSERVICE_DEPLOY} not found in namespace ${NAMESPACE}"
fi

# Figure out the actual container name (first container)
US_CTN="$(kubectl -n "${NAMESPACE}" get deploy "${USERSERVICE_DEPLOY}" -o jsonpath='{.spec.template.spec.containers[0].name}' 2>/dev/null || true)"
[[ -z "${US_CTN}" ]] && die "Could not determine container name for ${USERSERVICE_DEPLOY}"

# Strategic-merge patch to add volume, mount, and envs (idempotent by name merge)
kubectl -n "${NAMESPACE}" patch deploy "${USERSERVICE_DEPLOY}" -p "$(cat <<PATCH
{
  "spec": {
    "template": {
      "spec": {
        "volumes": [
          {
            "name": "jwt-private",
            "secret": {
              "secretName": "${JWT_SECRET_NAME}",
              "items": [{"key": "jwtRS256.key", "path": "privatekey"}]
            }
          }
        ],
        "containers": [
          {
            "name": "${US_CTN}",
            "volumeMounts": [
              {"name": "jwt-private", "mountPath": "/tmp/.ssh", "readOnly": true}
            ],
            "env": [
              {"name":"PRIV_KEY_PATH","value":"${PRIV_KEY_PATH}"},
              {"name":"PRIVATE_KEY_PATH","value":"${PRIV_KEY_PATH}"},
              {"name":"JWT_PRIVATE_KEY_PATH","value":"${PRIV_KEY_PATH}"},
              {"name":"LOCAL_ROUTING_NUM","value":"${ROUTING}"}
            ]
          }
        ]
      }
    }
  }
}
PATCH
)" >/dev/null

kubectl -n "${NAMESPACE}" rollout restart deploy "${USERSERVICE_DEPLOY}"

# ---------- 5) Ensure transactionhistory uses PUB_KEY_PATH + routing ----------
bold "[5/8] Ensure transactionhistory env from ConfigMap + routing"
if ! kubectl -n "${NAMESPACE}" get deploy "${HISTORY_DEPLOY}" >/dev/null 2>&1; then
  die "Deployment ${HISTORY_DEPLOY} not found in namespace ${NAMESPACE}"
fi

kubectl -n "${NAMESPACE}" set env deploy "${HISTORY_DEPLOY}" LOCAL_ROUTING_NUM="${ROUTING}" >/dev/null
# PUB_KEY_PATH comes via envFrom: environment-config (already set in your manifests)
kubectl -n "${NAMESPACE}" rollout restart deploy "${HISTORY_DEPLOY}"

# ---------- 6) Fix frontend HISTORY_API_ADDR (host:port only) ----------
bold "[6/8] Ensure frontend ConfigMap service-api-config has HISTORY_API_ADDR"
kubectl -n "${NAMESPACE}" get configmap service-api-config >/dev/null 2>&1 || \
  kubectl -n "${NAMESPACE}" create configmap service-api-config

kubectl -n "${NAMESPACE}" patch configmap service-api-config --type merge -p \
  '{"data":{"HISTORY_API_ADDR":"transactionhistory:8080"}}'

kubectl -n "${NAMESPACE}" rollout restart deploy "${FRONTEND_DEPLOY}"

# ---------- 7) (Optional) Workload Identity fix for shared KSA ----------
if [[ "${APPLY_WI}" == "true" ]]; then
  bold "[7/8] Workload Identity binding for KSA ${KSA_SHARED} → GSA ${GSA_NAME}"
  if [[ -z "${PROJECT_ID}" ]]; then
    PROJECT_ID="$(gcloud config get-value core/project 2>/dev/null || true)"
  fi
  [[ -z "${PROJECT_ID}" ]] && die "PROJECT_ID is required for WI (set --project or gcloud config)"
  need gcloud
  GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
  gcloud iam service-accounts describe "${GSA_EMAIL}" --project "${PROJECT_ID}" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "${GSA_NAME}" --project "${PROJECT_ID}"
  gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
    --project "${PROJECT_ID}" --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_SHARED}]" >/dev/null
  kubectl -n "${NAMESPACE}" annotate serviceaccount "${KSA_SHARED}" \
    iam.gke.io/gcp-service-account="${GSA_EMAIL}" --overwrite
  # Minimal Cloud Ops roles (quiet the 403s)
  for role in roles/cloudtrace.agent roles/monitoring.metricWriter roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${GSA_EMAIL}" --role="${role}" >/dev/null
  done
  kubectl -n "${NAMESPACE}" rollout restart deploy >/dev/null 2>&1 || true
else
  yellow "Skipping Workload Identity binding (--no-wi)"
fi

# ---------- 8) (Optional) Smoke test ----------
if [[ "${DO_SMOKE}" == "true" ]]; then
  bold "[8/8] Smoke test — /healthy and /transactions/${ACCOUNT_ID}"
  # Quick health
  kubectl -n "${NAMESPACE}" run th-health --rm -it --restart=Never --image=curlimages/curl:8.10.1 -- \
    sh -lc 'curl -sS http://transactionhistory:8080/healthy || true' || true

  # Build a short-lived dev JWT using the secret inside the cluster
  TMPK="$(mktemp)"
  kubectl -n "${NAMESPACE}" get secret "${JWT_SECRET_NAME}" -o jsonpath='{.data.jwtRS256\.key}' | base64 -d > "${TMPK}"
  chmod 600 "${TMPK}"
  IAT=$(date +%s); EXP=$((IAT+900)) # 15 minutes
  HDR=$(printf '{"alg":"RS256","typ":"JWT"}' | python3 - <<'PY'
import sys,base64; print(base64.urlsafe_b64encode(sys.stdin.buffer.read()).decode().rstrip("="))
PY
)
  PAYLOAD=$(printf '{"iss":"https://save2win.auth","aud":"bank-of-anthos.history","sub":"%s","acct":"%s","scope":"history.read","iat":%s,"exp":%s}' \
    "${ACCOUNT_USER}" "${ACCOUNT_ID}" "${IAT}" "${EXP}" | python3 - <<'PY'
import sys,base64; print(base64.urlsafe_b64encode(sys.stdin.buffer.read()).decode().rstrip("="))
PY
)
  SIG=$(printf "%s.%s" "${HDR}" "${PAYLOAD}" | openssl dgst -sha256 -sign "${TMPK}" -binary | python3 - <<'PY'
import sys,base64; print(base64.urlsafe_b64encode(sys.stdin.buffer.read()).decode().rstrip("="))
PY
)
  JWT="${HDR}.${PAYLOAD}.${SIG}"
  rm -f "${TMPK}"

  # Call the endpoint
  kubectl -n "${NAMESPACE}" run th-call --rm -it --restart=Never --image=curlimages/curl:8.10.1 -- \
    sh -lc 'curl -sS -H "Authorization: Bearer '"${JWT}"'" \
      http://transactionhistory:8080/transactions/'"${ACCOUNT_ID}"' | head -n 40' || true
else
  yellow "Skipping smoke test (--no-smoke)"
fi

green "✔ Done. Frontend should now be able to display transaction history."
echo "If UI still blank:"
echo "  • Verify you login as ${ACCOUNT_USER} (owner of ${ACCOUNT_ID})"
echo "  • Check: kubectl -n ${NAMESPACE} logs deploy/${HISTORY_DEPLOY} --tail=200"
echo "  • Check: kubectl -n ${NAMESPACE} get configmap service-api-config -o yaml | sed -n '1,120p'"
