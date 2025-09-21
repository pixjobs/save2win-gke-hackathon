# Deployment Guide for Save2Win

This guide provides **step-by-step instructions** to deploy the base **Bank of Anthos** application onto a **Google Kubernetes Engine (GKE) Autopilot** cluster. Completing these steps prepares the foundational platform for the Save2Win features.

---

## ✅ Prerequisites

Ensure the following are installed and configured on your local machine:

- **Google Cloud Account**: A GCP project created with billing enabled.
- **Git**: To clone the project repository.
- **Google Cloud SDK (`gcloud`)**: Install per your OS — see the official [Installation Guide](https://cloud.google.com/sdk/docs/install).
- **Project Code**: The `save2win-gke-hackathon` repository cloned locally.

### Required `gcloud` Components
The deployment relies on specific components to interact with Kubernetes and build/deploy artifacts.

**Standard install (most setups):**
```bash
gcloud components install kubectl skaffold gke-gcloud-auth-plugin
```

**If your `gcloud` was installed via `apt` on Linux/WSL (component manager disabled):**
```bash
sudo apt-get update && sudo apt-get install   kubectl   google-cloud-cli-gke-gcloud-auth-plugin   google-cloud-cli-skaffold
```

> Tip: Verify installs
> ```bash
> gcloud --version
> kubectl version --client
> skaffold version
> ```

---

## 🧩 Step 1: Local Configuration

The deployment script uses a local env file to manage credentials securely. Create and configure this file before running any commands.

1) **Copy the example file** in the project root:
```bash
cp .env.example .env.local
```

2) **Edit `.env.local`** and fill in your Google Cloud details:

**File: `.env.local`**
```bash
# --- PRIVATE LOCAL CONFIGURATION ---
# This file is for your local setup only.
# It is ignored by Git and should NEVER be committed.

GCP_ACCOUNT_EMAIL="yang.pei@lgcgroup.com"
PROJECT_ID="gke-trial-472609"
CLUSTER_NAME="bank-of-anthos"
REGION="europe-west1"
```

> Note: Keep `.env.local` private (it's gitignored by default).

---

## ☸️ Step 2: Create the GKE Autopilot Cluster

Create the GKE cluster where the application will be deployed. This command reads values from your `.env.local` file.

1) **Load your environment variables:**
```bash
source .env.local
```

2) **Create the cluster:**
```bash
gcloud container clusters create-auto "$CLUSTER_NAME"   --project="$PROJECT_ID"   --region="$REGION"
```
- Uses the name, project, and region you defined.
- `create-auto` enables **Autopilot** mode to simplify cluster operations.

> ⏳ **Expected duration:** 5–10 minutes. The terminal returns to the prompt when the cluster is ready.

---

## 🚀 Step 3: Run the Automated Deployment Script

With your cluster running and local configuration set, run the deployment script. It handles authentication, cluster cleanup, and deployment via **Skaffold**.

1) **Make the script executable** (first time only):
```bash
chmod +x deploy-boa.sh
```

2) **Execute the deployment script:**
```bash
./deploy-boa.sh
```

**The script will:**
- Prompt you to authenticate to Google Cloud using the email in `.env.local`.
- Set your `kubectl` context to the new GKE cluster.
- Wipe the `default` namespace to ensure a clean deployment.
- Run `skaffold run` to build Bank of Anthos container images and deploy them.

> ⏳ **Expected duration:** 10–15 minutes for the first build and deploy.

---

## 🔍 Step 4: Verify the Deployment

Confirm that the application is running correctly.

1) **List Kubernetes services:**
```bash
kubectl get services
```

2) **Find the external IP** for the **frontend** service (some manifests use `frontend-external`). It can take a couple of minutes to appear.

**Example output:**
```text
NAME                 TYPE           CLUSTER-IP      EXTERNAL-IP     PORT(S)        AGE
...
frontend             LoadBalancer   10.44.12.129    35.187.95.173   80:31108/TCP   5m
...
```

3) **Open the app:** Copy the **EXTERNAL-IP** (e.g., `35.187.95.173`) into your browser. You should see the live **Bank of Anthos** application.

🎉 **Congratulations!** The base platform is now successfully deployed.

---

## 🛠️ Troubleshooting

- **Permission denied on script**  
  Ensure the file is executable:
  ```bash
  chmod +x deploy-boa.sh
  ```

- **`gke-gcloud-auth-plugin` not found**  
  This is a common local setup issue. Re-run the installation commands from **Prerequisites** to install the auth plugin for `kubectl`.

- **Skaffold build errors / permission issues**  
  Ensure the following APIs are enabled in your GCP project:
  - Cloud Build API
  - Artifact Registry API
  - Kubernetes Engine API

  Enable via console or CLI:
  ```bash
  gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com container.googleapis.com --project "$PROJECT_ID"
  ```

- **No EXTERNAL-IP yet**  
  LoadBalancer provisioning can take a few minutes. Re-run:
  ```bash
  kubectl get svc frontend
  ```
  (Or `frontend-external` if applicable.)

---

**Document version:** 1.1
