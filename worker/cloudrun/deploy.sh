#!/usr/bin/env bash
# Deploy pickfit.app to Google Cloud Run (project pickfit-app, asia-east1). Run from anywhere.
# Rebuilds src/generated/ from data/software first, then builds the image with Cloud Build.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PICKFIT_GCP_PROJECT:-pickfit-app}"
REGION="${PICKFIT_GCP_REGION:-asia-east1}"
ACCOUNT_ID="be5f9e827161c443f2ec29b99bfae347" # Cloudflare account holding D1 pickfit and R2 pickfit-videos
RUN_HOST="pickfit-461166503123.asia-east1.run.app"

npm run build:index

gcloud run deploy pickfit \
  --project "$PROJECT" --region "$REGION" --source . \
  --allow-unauthenticated --no-cpu-throttling \
  --cpu 1 --memory 512Mi --min-instances 0 --max-instances 4 --concurrency 80 --timeout 120 \
  --set-env-vars "^@^CLOUDFLARE_ACCOUNT_ID=${ACCOUNT_ID}@ALLOWED_HOSTS=pickfit.app,pickfit-mcp.ncchen99.workers.dev,${RUN_HOST}" \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest,CLOUDFLARE_API_TOKEN=cloudflare-api-token:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest" \
  --quiet
