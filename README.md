# abtahi.fyi

Private compiled-study pilot application built with Python 3.12 and FastAPI.

## Local setup

1. Create a local virtual environment: `python3 -m venv .venv`
2. Install dependencies: `.venv/bin/python -m pip install -e .[test]`
3. Run the test suite: `.venv/bin/python -m pytest -v`

## Constraints

- Production runtime is Python-only and carries no Node.js dependency.
- Firebase CLI or CI tooling, when introduced later, must use Node LTS 20, 22, or 24 only.
- Remote Firebase and Google Cloud resources are configured in later tasks, not in this baseline.
- Private sessions are Firebase-verified, allowlist-bound, and use Secure,
  HttpOnly, SameSite=Lax session and CSRF companion cookies.
- Private proposal mutations require `X-CSRF-Token` and `Idempotency-Key`.
  Connect and Edit require `reviewed_content`; Defer requires `defer_window`;
  a dismissal can be undone only with its dismissal operation ID.
- Learner-approved connections are stored and projected in the authenticated
  learner's private Firestore collections. They are never added to the public
  content loader, search index, feeds, or NetworkX cache.
- Source collection is available only to the configured privileged job identity.
  `APPROVED_FEED_URLS` is the registered-feed allowlist, and every source is
  archived privately before downstream processing. External proposal processing
  requires an exact learner/revision/purpose/provider consent grant.

## Production Release Operations

### 1. Release Configuration & Inputs
Non-secret release configuration is defined in `deploy/cloud-run.env.example`.
Copy this to `deploy/cloud-run.env` and populate environment-specific targets:
- `GCP_PROJECT_ID`: Target GCP project (e.g. `spatial-cat-489006-a4`)
- `GCP_REGION`: Cloud Run region (e.g. `us-central1`)
- `SERVICE_NAME`: Service identifier (e.g. `abtahi-fyi`)
- `ALLOWLISTED_EMAIL`: Learner owner email
- Secrets like `CSRF_SECRET` must reside in Secret Manager, never in code or unencrypted files.

### 2. Firestore Security Rules Deployment
Before service traffic commences, deploy the Zero-Trust Firestore rules:
```bash
firebase deploy --only firestore
```

### 3. Service Deployment to Cloud Run
Deploy the verified non-root container with the mandatory challenge label:
```bash
./deploy/deploy.sh
```
The script applies label `dev-tutorial=cloud-run-ai-challenge`, discovers the provider-issued HTTPS `SERVICE_URL`, and performs an automated smoke check against `$SERVICE_URL/healthz`.

### 4. Privileged Scheduled Work (Cloud Scheduler)
Configure OIDC-authenticated background jobs for feed collection and nightly synthesis:
```bash
./deploy/scheduler.sh
```
Scheduler calls are authenticated via dedicated Google OIDC service account tokens. Ordinary browser sessions and unauthenticated requests to maintenance endpoints receive `403 Forbidden`.

### 5. Operator Recovery & Rollback
- **Failed Readiness (`503 unavailable`)**: Check startup logs with `gcloud logging read "resource.labels.service_name=abtahi-fyi" --limit=20`. Verify projection database write permissions in `/app/data` and Secret Manager accessibility.
- **Rollback**: To revert to the previous known-good revision:
  ```bash
  gcloud run services update-traffic abtahi-fyi --to-revisions=PREVIOUS_REVISION=100 --region=us-central1
  ```
- **Post-Recovery Verification**: Verify `curl -fsS "$SERVICE_URL/health"` returns `{"status":"ok"}`.

### 6. Verified Production Release Record
- **Service Name**: `abtahi-fyi`
- **GCP Project**: `spatial-cat-489006-a4` (Region: `us-central1`)
- **Active Revision**: `abtahi-fyi-00002-2hg`
- **Mandatory Challenge Label**: `dev-tutorial=cloud-run-ai-challenge` (Verified)
- **Live Provider-Issued URL**: [https://abtahi-fyi-qvj33q6t2a-uc.a.run.app](https://abtahi-fyi-qvj33q6t2a-uc.a.run.app)
- **Direct Domain**: [https://abtahi-fyi-903682941870.us-central1.run.app](https://abtahi-fyi-903682941870.us-central1.run.app)
- **Readiness Verification**: Probed `/health` and `/healthz` returning HTTP `200 OK` (`{"status":"ok"}`).
- **Privileged Automation (Cloud Scheduler)**:
  - Service Account: `abtahi-fyi-scheduler@spatial-cat-489006-a4.iam.gserviceaccount.com` (Least-privilege `roles/run.invoker`)
  - Feed Ingestion Job: `abtahi-fyi-poll-feeds` (`0 */6 * * *`) -> `POST /api/poll-feeds` (OIDC Target)
  - Consolidation Job: `abtahi-fyi-consolidate` (`0 3 * * *`) -> `POST /api/consolidate` (OIDC Target)
- **Zero-Trust Rules**: Deployed via `firebase deploy --only firestore:rules,firestore:indexes` to project `spatial-cat-489006-a4`.

