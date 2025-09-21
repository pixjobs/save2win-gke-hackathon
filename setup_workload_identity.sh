#!/bin/bash

# ==============================================================================
#           *** The GKE Autopilot Workload Identity Fix ***
#
# This script is tailored for GKE Autopilot clusters where Workload Identity
# is enabled by default. It focuses only on the application and IAM layers.
# ==============================================================================

# --- Safety First: Exit immediately if a command fails.
set -e

# --- 1. Configuration - Please verify these values ---
export PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
export NAMESPACE="boa"
export KSA_NAME="bank-of-anthos-ksa"
export GSA_NAME="gke-workload-development"
# --- End of Configuration ---


# --- Script-internal variables ---
export GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color


# --- Script Start ---
echo -e "${BLUE}🚀 Starting Autopilot-specific Workload Identity setup...${NC}"
echo "------------------------------------------------------------"
echo "   Project:       ${PROJECT_ID}"
echo "   Namespace:     ${NAMESPACE}"
echo "------------------------------------------------------------"
echo ""

# --- STEP 1: CONFIGURE IAM AND KUBERNETES SERVICE ACCOUNTS ---
echo -e "${BLUE}[STEP 1/3] Ensuring all IAM and Kubernetes service accounts are correctly configured...${NC}"

# Create GSA (if not exists)
if ! gcloud iam service-accounts describe "${GSA_EMAIL}" --project="${PROJECT_ID}" &> /dev/null; then
  echo "  -> Creating Google Service Account (GSA)..."
  gcloud iam service-accounts create "${GSA_NAME}" --project="${PROJECT_ID}" --display-name="Bank of Anthos Workload Identity SA"
fi
# Create KSA (if not exists)
if ! kubectl get serviceaccount "${KSA_NAME}" --namespace "${NAMESPACE}" &> /dev/null; then
  echo "  -> Creating Kubernetes Service Account (KSA)..."
  kubectl create serviceaccount "${KSA_NAME}" --namespace "${NAMESPACE}"
fi

# Link the two accounts
echo "  -> Linking KSA to GSA and annotating..."
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]" \
  --project="${PROJECT_ID}"

kubectl annotate serviceaccount "${KSA_NAME}" \
  --namespace "${NAMESPACE}" \
  "iam.gke.io/gcp-service-account=${GSA_EMAIL}" \
  --overwrite

echo "  -> Service Accounts configured."

# --- STEP 2: GRANT NECESSARY ROLES TO THE GSA ---
echo -e "\n${BLUE}[STEP 2/3] Granting necessary observability roles to the GSA...${NC}"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${GSA_EMAIL}" --role="roles/logging.logWriter" --condition=None &> /dev/null
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${GSA_EMAIL}" --role="roles/monitoring.metricWriter" --condition=None &> /dev/null
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${GSA_EMAIL}" --role="roles/cloudtrace.agent" --condition=None &> /dev/null
echo "  -> Roles granted."

# --- STEP 3: PATCH DEPLOYMENTS TO USE THE NEW KSA ---
echo -e "\n${BLUE}[STEP 3/3] Patching all deployments to use the configured service account...${NC}"
for dep in $(kubectl get deployments -n "${NAMESPACE}" -o name); do
  kubectl patch "${dep}" -n "${NAMESPACE}" -p '{"spec":{"template":{"spec":{"serviceAccountName":"'"${KSA_NAME}"'"}}}}'
done
echo "  -> All deployments have been patched, triggering a rolling restart."

# --- FINAL OUTPUT ---
echo -e "\n${GREEN}✅✅✅ COMPLETE! The Autopilot configuration has been applied.${NC}"
echo "The pods will now restart with the correct service account and permissions."
echo -e "\n${BLUE}To verify, run this command after the pods are 'Running':${NC}"
echo "kubectl get pod -n ${NAMESPACE} -l app=balancereader -o yaml | grep serviceAccountName"
echo "(The output should be 'bank-of-anthos-ksa')"