# Publishing a service through Tarnwave

Tarnwave is the gateway that sits in front of every internal service. It checks access tokens, limits the number of requests per client and records metrics for the operations team. This page explains how to register a new service and how to test it before you announce it to other teams.

## Register the service

Each service needs a short description file in its repository. The gateway reads this file during every deployment, so keep it next to your source code.

```yaml
# Description file read by the gateway on every deployment
name: invoice-export
owner: finance-platform
upstream: http://invoice-export.internal:8080
rate_limit_per_minute: 600
```

The name must be unique and may only contain lowercase letters, digits and hyphens. Requests that exceed the limit receive the status code 429 and should be retried after a short pause.

## Test the route

After the deployment, send a test request from your laptop. Replace the token with one that you generate in the developer portal, and never paste real tokens into chat messages or tickets.

```bash
# Ask the gateway whether the new route answers
curl -H "Authorization: Bearer $TARNWAVE_TOKEN" \
  https://gateway.example.com/invoice-export/health
```

A response with the status code 200 means that the route works. If you receive the status code 404, the gateway has not loaded your description file yet, so wait 5 minutes and try again.

## Monitoring

Tarnwave sends request counts and response times to the metrics dashboard every 60 seconds. You can find the dashboard for your service at <https://metrics.example.com/d/gateway?var-service=invoice-export>. An alert is sent to the owning team when more than 5 percent of the requests fail during a period of 10 minutes.

## Retiring a service

When a service is no longer needed, remove its description file and announce the change at least 7 days before the removal. Clients that still call the old route will receive the status code 410. The [retirement checklist](https://docs.example.com/gateway/retire?version=2#checklist) lists every step, including how to archive the logs.

For questions about the gateway, write to the platform team or check the status page at https://status.example.com before you open a ticket.
