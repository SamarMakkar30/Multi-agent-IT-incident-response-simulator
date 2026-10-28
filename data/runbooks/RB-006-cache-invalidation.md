# RB-006: Distributed Cache Invalidation Runbook

## Symptoms
- Stale data served to users or cache stampede causing downstream database spikes.

## Action Steps
1. Trigger targeted cache key invalidation for affected partitions.
2. Warm critical hot keys before re-enabling full cache ingress.

