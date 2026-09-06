#!/usr/bin/env bash
# ==============================================================================
# Cloud Scheduler OIDC Automation Setup Script for abtahi.fyi
# Configures least-privilege service account, run.invoker IAM, and OIDC jobs.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Load environment configuration if present
if [[ -f "${SCRIPT_DIR}/cloud-run.env" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/cloud-run.env"
fi

GCP_PROJECT_ID="${GCP_PROJECT_ID:-spatial-cat-489006-a4}"
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-abtahi-fyi}"
SA_NAME="${SCHEDULER_SA_NAME:-abtahi-fyi-scheduler}"
SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# Discover Service URL if not provided
if [[ -z "${SERVICE_URL:-}" ]]; then
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --project="${GCP_PROJECT_ID}" \
        --region="${GCP_REGION}" \
        --format='value(status.url)' 2>/dev/null || echo "")
fi

if [[ -z "${SERVICE_URL}" ]]; then
    echo "ERROR: Could not resolve SERVICE_URL. Please specify SERVICE_URL or deploy service first." >&2
    exit 1
fi

echo "================================================================================"
echo "Configuring Cloud Scheduler Workload Identity for ${SERVICE_NAME}"
echo "Service Account: ${SA_EMAIL}"
echo "Target Audience: ${SERVICE_URL}"
echo "================================================================================"

# 1. Ensure Dedicated Service Account Exists
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating dedicated Scheduler service account: ${SA_EMAIL}..."
    gcloud iam service-accounts create "${SA_NAME}" \
        --project="${GCP_PROJECT_ID}" \
        --display-name="abtahi.fyi Cloud Scheduler Invoker"
fi

# Allow Cloud Scheduler service agent to create OIDC tokens for this service account
PROJECT_NUMBER=$(gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
    --project="${GCP_PROJECT_ID}" \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountTokenCreator" \
    --quiet >/dev/null 2>&1 || true

# 2. Grant Least-Privilege roles/run.invoker on Cloud Run Service
echo "Granting roles/run.invoker to ${SA_EMAIL} on ${SERVICE_NAME}..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --project="${GCP_PROJECT_ID}" \
    --region="${GCP_REGION}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.invoker" \
    --quiet


# 3. Schedule Feed Ingestion Job (Every 6 Hours)
JOB_POLL="${SERVICE_NAME}-poll-feeds"
echo "Creating/Updating Cloud Scheduler Job: ${JOB_POLL}..."
if gcloud scheduler jobs describe "${JOB_POLL}" --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${JOB_POLL}" \
        --location="${GCP_REGION}" \
        --project="${GCP_PROJECT_ID}" \
        --schedule="0 */6 * * *" \
        --uri="${SERVICE_URL}/api/poll-feeds" \
        --http-method=POST \
        --oidc-service-account-email="${SA_EMAIL}" \
        --oidc-token-audience="${SERVICE_URL}"
else
    gcloud scheduler jobs create http "${JOB_POLL}" \
        --location="${GCP_REGION}" \
        --project="${GCP_PROJECT_ID}" \
        --schedule="0 */6 * * *" \
        --uri="${SERVICE_URL}/api/poll-feeds" \
        --http-method=POST \
        --oidc-service-account-email="${SA_EMAIL}" \
        --oidc-token-audience="${SERVICE_URL}"
fi

# 4. Schedule Nightly Consolidation Dream Cycle (03:00 UTC Daily)
JOB_CONSOLIDATE="${SERVICE_NAME}-consolidate"
echo "Creating/Updating Cloud Scheduler Job: ${JOB_CONSOLIDATE}..."
if gcloud scheduler jobs describe "${JOB_CONSOLIDATE}" --location="${GCP_REGION}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${JOB_CONSOLIDATE}" \
        --location="${GCP_REGION}" \
        --project="${GCP_PROJECT_ID}" \
        --schedule="0 3 * * *" \
        --uri="${SERVICE_URL}/api/consolidate" \
        --http-method=POST \
        --oidc-service-account-email="${SA_EMAIL}" \
        --oidc-token-audience="${SERVICE_URL}"
else
    gcloud scheduler jobs create http "${JOB_CONSOLIDATE}" \
        --location="${GCP_REGION}" \
        --project="${GCP_PROJECT_ID}" \
        --schedule="0 3 * * *" \
        --uri="${SERVICE_URL}/api/consolidate" \
        --http-method=POST \
        --oidc-service-account-email="${SA_EMAIL}" \
        --oidc-token-audience="${SERVICE_URL}"
fi

echo "================================================================================"
echo "CLOUD SCHEDULER JOBS CONFIGURED SUCCESSFULLY!"
echo "Feed Poller: ${JOB_POLL} -> ${SERVICE_URL}/api/poll-feeds"
echo "Consolidator: ${JOB_CONSOLIDATE} -> ${SERVICE_URL}/api/consolidate"
echo "================================================================================"
