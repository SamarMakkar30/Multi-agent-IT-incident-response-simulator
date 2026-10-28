# RB-008: Database Schema Migration Incompatibility Runbook

## Symptoms
- Deployment included destructive schema changes (column dropped, table renamed, constraints added).
- Service errors occurred post-deploy, but rolling back application code will crash because older code expects deleted schema.

## Action Steps
1. STRICT RULE: DO NOT ROLLBACK. Code rollback to previous version will immediately fail with schema syntax errors.
2. Check if a feature flag can disable the failing code path without rollback.
3. If data corruption is occurring, failover service to read-only replica or maintenance mode while forward-fix patch is applied.
4. Prepare emergency hotfix forward-deploy.
