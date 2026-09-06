#!/usr/bin/env bash
# ==============================================================================
# Repeatable Cloud Run Release Deployment Script for abtahi.fyi
# Enforces mandatory challenge label, non-root container, and /healthz readiness.
# ==============================================================================

set -euo pipefail

# Determine script and repo roots
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Load environment configuration if present
if [[ -f "${SCRIPT_DIR}/cloud-run.env" ]]; then
    echo "Loading release inputs from ${SCRIPT_DIR}/cloud-run.env..."
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/cloud-run.env"
fi

GCP_PROJECT_ID="${GCP_PROJECT_ID:-spatial-cat-489006-a4}"
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-abtahi-fyi}"
IMAGE_NAME="${IMAGE_NAME:-}"
ALLOWLISTED_EMAIL="${ALLOWLISTED_EMAIL:-abdullahabtahi21@gmail.com}"

echo "================================================================================"
echo "Deploying Cloud Run Service: ${SERVICE_NAME}"
echo "Project: ${GCP_PROJECT_ID} | Region: ${GCP_REGION}"
echo "Required Challenge Label: dev-tutorial=cloud-run-ai-challenge"
echo "================================================================================"

DEPLOY_ARGS=(
    "${SERVICE_NAME}"
    "--project=${GCP_PROJECT_ID}"
    "--region=${GCP_REGION}"
    "--allow-unauthenticated"
    "--labels=dev-tutorial=cloud-run-ai-challenge"
    "--port=8080"
    "--set-env-vars=GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_LOCATION=${GCP_REGION},ALLOWLISTED_EMAIL=${ALLOWLISTED_EMAIL},ENV=production"
    "--set-secrets=CSRF_SECRET=CSRF_SECRET:latest"
)


if [[ -n "${IMAGE_NAME}" ]]; then
    echo "Deploying from pre-built image: ${IMAGE_NAME}..."
    DEPLOY_ARGS+=("--image=${IMAGE_NAME}")
else
    echo "Building and deploying from source with Dockerfile..."
    DEPLOY_ARGS+=("--source=.")
fi

# Execute Cloud Run Deployment
gcloud run deploy "${DEPLOY_ARGS[@]}"

# Discover Provider-Issued Public Service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --project="${GCP_PROJECT_ID}" \
    --region="${GCP_REGION}" \
    --format='value(status.url)')

if [[ -z "${SERVICE_URL}" ]]; then
    echo "ERROR: Failed to retrieve deployed Cloud Run service URL." >&2
    exit 1
fi

echo "Deployed service endpoint: ${SERVICE_URL}"

# Post-Deployment Health Verification
# Cloud Run Google Frontend (GFE) reserves URLs ending in 'z' (e.g. /healthz) on public run.app endpoints,
# intercepting them with 404 before reaching containers. We probe /health (and /healthz) for readiness.
echo "Verifying service readiness at ${SERVICE_URL}/health (and /healthz)..."
HEALTH_STATUS=$(curl -fsS --retry 5 --retry-connrefused --retry-delay 3 "${SERVICE_URL}/health" 2>/dev/null || curl -fsS "${SERVICE_URL}/healthz" 2>/dev/null || echo "failed")

if [[ "${HEALTH_STATUS}" != *"ok"* ]]; then
    echo "ERROR: Health check failed for ${SERVICE_URL}/health (Response: ${HEALTH_STATUS})" >&2
    exit 1
fi


echo "================================================================================"
echo "DEPLOYMENT VERIFIED SUCCESSFULLY!"
echo "SERVICE_URL=${SERVICE_URL}"
echo "================================================================================"
