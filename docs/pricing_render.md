# Render Pricing Reference

Pricing retrieved June 2026. Check render.com/pricing for current rates.

## Services used by this project

### Static site — Vue frontend
**Free**, no expiry. Includes CDN, continuous deploys from Git, custom domains with managed TLS.

### Web services — Node.js API and Python sim engine
Billed per instance, prorated by the second.

| Tier | Price/month | RAM | CPU |
|---|---|---|---|
| Free | $0 | 512 MB | 0.1 |
| Starter | $7 | 512 MB | 0.5 |
| Standard | $25 | 2 GB | 1 |

Free tier limitation: services spin down after 15 minutes of inactivity and have a cold start delay on the next request. Acceptable for development; use Starter or Standard for production.

### Cron job — data pipeline
Billed per minute of compute time (only while the job is running, not while idle). Minimum $1/month.

| Tier | Price/minute | RAM | CPU |
|---|---|---|---|
| Starter | $0.00016 | 512 MB | 0.5 |
| Standard | $0.00058 | 2 GB | 1 |

The pipeline runs once per week for a few minutes. Expected cost: well under the $1/month minimum.

## Not used

**Render Postgres** — not applicable; database is on Supabase.

## Other charges (if applicable)

- Bandwidth: 5 GB/month included, then $0.15/GB. A small fantasy league generates minimal API traffic; the free allowance is unlikely to be exceeded.
- Build pipeline: 500 minutes/month included, then $5 per 1,000 minutes
- Custom domains: 2 included, then $0.25/domain/month
