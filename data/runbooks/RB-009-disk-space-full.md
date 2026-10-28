# RB-009: Ephemeral Disk Full Runbook

## Symptoms
- Pods failing health checks with `no space left on device` or write failures on local disk mounts.

## Action Steps
1. Evacuate stale container logs and rotated core dumps.
2. Restart pods on fresh nodes with clean ephemeral volumes.
