# One-time setup: let GitHub Actions deploy pickfit.app to Cloud Run

The `deploy-cloudrun` job in `.github/workflows/worker.yml` deploys pickfit.app on every push to `main` that
changes the site. It logs in to GCP with Workload Identity Federation: GitHub gives the job a short-lived OIDC
token, GCP trades it for a token of a deploy service account. No JSON key is created or stored.

Until the two repository variables at the end are set, the job is skipped (grey, not red). Run the commands
below once, from a machine where `gcloud` is logged in as a project owner and `gh` is logged in to GitHub.

Facts these commands use (looked up 2026-11-20 with read-only `gcloud` calls):

- project `pickfit-app`, project number `461166503123`, region `asia-east1`, repository `ncchen99/pickfit`;
- the service runs as the Compute Engine default service account `461166503123-compute@developer.gserviceaccount.com`,
  which is also the Cloud Build default service account for this project, and it already has `roles/editor`;
- `run`, `cloudbuild`, `artifactregistry`, `secretmanager` and `iamcredentials` are already enabled; no
  Workload Identity pool exists yet.

## 1. Variables for this shell

```bash
PROJECT=pickfit-app
PROJECT_NUMBER=461166503123
REPO=ncchen99/pickfit
DEPLOY_SA=github-deploy@${PROJECT}.iam.gserviceaccount.com
RUNTIME_SA=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com
```

## 2. APIs

```bash
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project "$PROJECT"
```

Already-enabled APIs are left as they are. `sts` is the token exchange Workload Identity Federation uses.

## 3. The pool and GitHub's OIDC provider, limited to this repository's main branch

```bash
gcloud iam workload-identity-pools create github \
  --project "$PROJECT" --location global --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc pickfit \
  --project "$PROJECT" --location global --workload-identity-pool github \
  --display-name "ncchen99/pickfit main" \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition "assertion.repository == '${REPO}' && assertion.ref == 'refs/heads/main'"
```

A token from any other repository, a fork, a pull request or another branch is refused by the provider itself.

## 4. The deploy service account and its roles

```bash
gcloud iam service-accounts create github-deploy \
  --project "$PROJECT" --display-name "GitHub Actions: deploy pickfit to Cloud Run"

for role in roles/run.sourceDeveloper roles/run.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:${DEPLOY_SA}" --role "$role" --condition None
done

# Deploy a revision that runs as the runtime service account, and start builds that run as it.
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --project "$PROJECT" --member "serviceAccount:${DEPLOY_SA}" --role roles/iam.serviceAccountUser
```

Why these, from Google's "Deploy from source code" page (Required roles) and the Cloud Run IAM roles reference:

- `roles/run.sourceDeveloper`: what `gcloud run deploy --source` needs besides Cloud Run itself: start Cloud Build
  builds, create and read the `cloud-run-source-deploy` Artifact Registry repository, upload the source to the
  Cloud Build bucket. It replaces the older set of `cloudbuild.builds.editor` + `artifactregistry.writer` +
  `storage.admin`, so those are not granted.
- `roles/serviceusage.serviceUsageConsumer`: named by the same page; lets the account use the project's APIs.
- `roles/iam.serviceAccountUser` on the runtime service account only (not on the project): needed to deploy a
  revision that runs as that account. Here it is also the Cloud Build service account.
- `roles/run.admin` (judgement call): `deploy.sh` passes `--allow-unauthenticated`, which sets the service's IAM
  policy (`run.services.setIamPolicy`); among predefined roles only `run.admin` has that permission. It also
  lets the job move traffic back to an earlier revision (`update-traffic`), which `run.sourceDeveloper` covers
  too. If you prefer less, drop `run.admin` and remove `--allow-unauthenticated` from `deploy.sh` (the service is
  already public and stays public), then test one deploy.
- No Secret Manager role (judgement call): `--set-secrets` only names the secrets; the running service reads them
  as the runtime service account, which already can. If a deploy fails with a secret permission error, add
  `roles/secretmanager.secretAccessor` to `DEPLOY_SA` on the four secrets.
- The Cloud Build service account needs `roles/run.builder` per Google's page; it already has `roles/editor`,
  which covers it, so nothing to do. If you ever take `editor` away, grant `roles/run.builder` to `RUNTIME_SA`.

## 5. Let the GitHub job act as the deploy account

```bash
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --project "$PROJECT" --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${REPO}"
```

## 6. Tell the workflow (repository variables, not secrets: neither value is secret)

```bash
gh variable set GCP_WIF_PROVIDER --repo "$REPO" \
  --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/providers/pickfit"
gh variable set GCP_DEPLOY_SA --repo "$REPO" --body "$DEPLOY_SA"
```

New pools, providers and bindings can take up to 5 minutes to work. The next push to `main` that touches the
site deploys; or run the workflow by hand: `gh workflow run worker.yml --ref main`.

## What the job does

1. Decides whether the push changes the site (`scripts/cloudrun_deploy.py changed`); a manual run always deploys.
2. Records the revision serving now (`serving`).
3. Runs `worker/cloudrun/deploy.sh`.
4. `verify`: waits up to 5 minutes for `https://pickfit.app/` to report the `data_sha256` just built and at least
   1000 entries, then sends `/mcp` a `tools/list`. If either fails, it runs
   `gcloud run services update-traffic pickfit --to-revisions=<previous>=100` and the job fails.

After such a rollback the traffic stays pinned to the old revision; the next deploy moves it to its own new
revision before checking.

## Cost

- Cloud Build: each deploy is one build of a few minutes on the default machine. Cloud Build's free tier is
  2,500 build-minutes a month on the default pool (check the current Cloud Build pricing page); a few deploys a
  day stays inside it.
- Artifact Registry: each deploy adds an image of about 100 MB to `cloud-run-source-deploy`; storage over 0.5 GB
  is billed (about US$0.10 per GB a month). Delete old images now and then, or add a cleanup policy.
- GitHub Actions minutes: the repository's normal allowance. Workload Identity Federation itself is free.

## Turn it off or undo it

- Pause deploys: `gh variable delete GCP_DEPLOY_SA --repo ncchen99/pickfit` (the job skips again). Set it back
  to resume.
- Roll back by hand: `gcloud run revisions list --service pickfit --project pickfit-app --region asia-east1`, then
  `gcloud run services update-traffic pickfit --project pickfit-app --region asia-east1 --to-revisions=REVISION=100`.
  Back to "latest revision gets the traffic": `... update-traffic pickfit ... --to-latest`.
- Remove access entirely:

```bash
gcloud iam workload-identity-pools providers delete pickfit --project pickfit-app --location global --workload-identity-pool github
gcloud iam service-accounts delete "github-deploy@pickfit-app.iam.gserviceaccount.com" --project pickfit-app
```
