# RB-007: Circuit Breaker Reset Runbook

## Symptoms
- Circuit breaker tripped open for a downstream service, rejecting all calls immediately.

## Action Steps
1. Verify downstream service has restored health and latency has normalized.
2. Manually transition breaker from OPEN to HALF-OPEN to allow canary probe traffic.

