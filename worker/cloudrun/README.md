# pickfit on Google Cloud Run (retired 2026-11-22)

> **Retired on 2026-11-22.** The Cloud Run service is shut down and CI no longer deploys it; https://pickfit.app is
> served by the Cloudflare Worker `pickfit-mcp` again (the `routes` in `../wrangler.jsonc`). This directory stays
> for the record, and `../test/cloudrun.test.ts` still runs against it. The text below describes 2026-11-18 to 11-22.

Since 2026-11-18, https://pickfit.app is served by Google Cloud Run: service `pickfit` in GCP project
`pickfit-app`, region `asia-east1` (Taiwan). The code is the same Worker code in `../src/`; `server.ts`
runs it in Node 24 behind `node:http`.

| Worker binding | On Cloud Run |
|---|---|
| `vars` | Read from `../wrangler.jsonc` (top level), environment variables override them |
| D1 `DB` (`pickfit`) | Same database, through the Cloudflare REST API (`bindings.ts` `remoteD1`) |
| R2 `VIDEOS` (`pickfit-videos`) | Same bucket, through R2's S3 API (`bindings.ts` `remoteR2`) |
| Static assets `../public` | Served by `server.ts`, with the rules in `public/_headers` |
| `WEB_RATE_LIMITER` | Not bound: `src/web.ts` falls back to its per-instance count |
| `ctx.waitUntil` | The promise runs on; the service has CPU always allocated (`--no-cpu-throttling`) |

The database and the bucket stay on Cloudflare, so the Python pipeline (`pickfit/d1.py`, `wrangler d1 execute`)
works unchanged. The Worker `pickfit-mcp` still runs on `pickfit-mcp.ncchen99.workers.dev` for MCP clients
configured with that address; it no longer has a route on pickfit.app.

## Secrets (GCP Secret Manager, project `pickfit-app`)

- `anthropic-api-key`: the Anthropic API key.
- `cloudflare-api-token`: Cloudflare user token "pickfit cloud run (D1 edit, R2 read)", scoped to D1 Edit and
  Workers R2 Storage Read on this account.
- `r2-access-key-id`, `r2-secret-access-key`: that token's id and the SHA-256 of its value, which is how R2's
  S3 API accepts an API token.

## Deploy

```bash
worker/cloudrun/deploy.sh
```

It rebuilds `src/generated/` and runs `gcloud run deploy --source .` from `worker/` (`Dockerfile`,
`.gcloudignore`). The domain mapping `pickfit.app` → `pickfit` was made once with
`gcloud beta run domain-mappings create`; DNS for pickfit.app (Cloudflare, DNS only) points at Google.

`ALLOWED_HOSTS` comes from `../wrangler.jsonc` (top-level `vars`) plus the run.app host (`config.ts`); change the
host list there, not in `deploy.sh`.

CI (`.github/workflows/worker.yml`, job `deploy-cloudrun`) runs the same script on pushes to `main` that change
the site, then checks pickfit.app serves the new data and rolls back if not (`scripts/cloudrun_deploy.py`). It
needs a one-time GCP setup: [setup-ci-wif.md](setup-ci-wif.md).

## Local run

```bash
cd worker && npm run build:index
CLOUDFLARE_ACCOUNT_ID=… CLOUDFLARE_API_TOKEN=… CANONICAL_HOST= PORT=8099 node cloudrun/server.ts
```
