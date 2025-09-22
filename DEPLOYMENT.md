🏆 Save2Win: Complete Deployment Guide

This guide provides step-by-step instructions to deploy the **Save2Win
application**, which consists of two main parts:

-   Part 1: The Base Platform --- Deploying the original Bank of Anthos
    application onto a GKE Autopilot cluster.
-   Part 2: The AI Extension --- Deploying your new microservices
    (frontend, engine, mcp) and the Ingress controller to enable AI
    features and seamless login.

------------------------------------------------------------------------

✅ Prerequisites

Ensure the following are installed and configured on your local machine:

-   Google Cloud Account: A GCP project created with billing enabled.
-   Git: To clone the project repository.
-   Google Cloud SDK (gcloud): Install per your OS --- see the official
    Installation Guide.
-   Project Code: The save2win-gke-hackathon repository cloned locally.

Required gcloud Components

The deployment relies on specific components to interact with Kubernetes
and build/deploy artifacts.

Standard install (most setups): gcloud components install kubectl
skaffold gke-gcloud-auth-plugin

If installed via apt on Linux/WSL (component manager disabled): sudo
apt-get update && sudo apt-get install kubectl
google-cloud-cli-gke-gcloud-auth-plugin google-cloud-cli-skaffold

Tip: Verify installs with: gcloud --version kubectl version --client
skaffold version

------------------------------------------------------------------------

Part 1: Deploying the Bank of Anthos Foundation

These steps prepare the foundational platform for the Save2Win features.

Step 1: Local Configuration cp .env.example .env.local

Edit .env.local: GCP_ACCOUNT_EMAIL="your-email@example.com"
PROJECT_ID="your-gcp-project-id" CLUSTER_NAME="bank-of-anthos"
REGION="europe-west1" AR_REPO_NAME="bank-of-anthos-repo"

Step 2: Create the GKE Autopilot Cluster source .env.local gcloud
container clusters create-auto "$CLUSTER_NAME" --project="$PROJECT_ID"
--region="\$REGION"

Step 3: Deploy the Bank of Anthos Application cd bank-of-anthos
./deploy.sh kubectl

Step 4: Verify Deployment kubectl get services -n boa

------------------------------------------------------------------------

Part 2: Deploying the Save2Win AI Extension

Step 5: One-Time Setup cd .. gcloud artifacts repositories create
"$AR_REPO_NAME" --repository-format=docker --location="$REGION"
--project="\$PROJECT_ID"

Permission script: source .env.local export NAMESPACE="boa" \# Save2Win
Engine export GCSA_NAME="save2win-engine-gcsa" export
KSA_NAME="save2win-engine-sa" gcloud iam service-accounts create
${GCSA_NAME} --project=${PROJECT_ID} gcloud projects
add-iam-policy-binding
${PROJECT_ID} --member="serviceAccount:${GCSA_NAME}@\${PROJECT_ID}.iam.gserviceaccount.com"
--role="roles/aiplatform.user" gcloud iam service-accounts
add-iam-policy-binding
${GCSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com
--role="roles/iam.workloadIdentityUser"
--member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/\${KSA_NAME}\]"

# MCP Service

export GCSA_NAME="mcp-service-gcsa" export KSA_NAME="mcp-service-sa"
gcloud iam service-accounts create ${GCSA_NAME} --project=${PROJECT_ID}
gcloud projects add-iam-policy-binding
${PROJECT_ID} --member="serviceAccount:${GCSA_NAME}@\${PROJECT_ID}.iam.gserviceaccount.com"
--role="roles/aiplatform.user" gcloud iam service-accounts
add-iam-policy-binding
${GCSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com
--role="roles/iam.workloadIdentityUser"
--member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/\${KSA_NAME}\]"

Step 6: Deploy Microservices skaffold run -p gcb
--default-repo="$REGION-docker.pkg.dev/$PROJECT_ID/\$AR_REPO_NAME"

Annotate Service Accounts: kubectl annotate serviceaccount
save2win-engine-sa --namespace boa
iam.gke.io/gcp-service-account=save2win-engine-gcsa@${PROJECT_ID}.iam.gserviceaccount.com --overwrite kubectl annotate serviceaccount mcp-service-sa --namespace boa iam.gke.io/gcp-service-account=mcp-service-gcsa@${PROJECT_ID}.iam.gserviceaccount.com
--overwrite

Final Run: skaffold dev -p gcb
--default-repo="$REGION-docker.pkg.dev/$PROJECT_ID/\$AR_REPO_NAME"

Step 7: Verify and Use kubectl get ingress -n boa save2win-ingress

Open browser at Ingress IP → Login with Bank of Anthos → See Save2Win
Dashboard.
