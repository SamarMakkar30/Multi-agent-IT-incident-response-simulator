# RB-001: Deployment Rollback Runbook

## Symptoms
- Sudden spike in HTTP 5xx error rates, unhandled exceptions, or latency immediately following a software release.
- Deployment occurred within the last 60 minutes.
- Downstream dependencies and infrastructure metrics (CPU, memory, database) are healthy.

## Action Steps
1. Verify the previous stable version in `data/deploys.json`.
2. Inspect whether the deployment included breaking database schema migrations.
   - If `breaking_db_migration == false`: Proceed with rollback to the previous version.
   - If `breaking_db_migration == true`: DO NOT ROLLBACK (see RB-008). Rollback will cause catastrophic schema mismatch.
3. Trigger deployment pipeline rollback to the previous stable release artifact.
4. Monitor service error rate for 5 minutes post-rollback to verify stabilization.
