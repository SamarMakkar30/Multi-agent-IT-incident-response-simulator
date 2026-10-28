# RB-003: External Provider Gateway Failover Runbook

## Symptoms
- Outbound requests to a third-party partner or upstream payment processor timing out or returning HTTP 502/503/504.
- Internal service logic is healthy, but provider latency or error rates spike.
- Secondary redundant provider is configured, warm, and reporting healthy status.

## Action Steps
1. Verify the health status of the secondary provider (`check_failover_readiness`).
2. Confirm sync replication and quota capacity on the secondary provider.
3. Switch active traffic routing in the gateway configuration from `primary` to `secondary`.
4. Validate that transaction success rates recover and latency returns within SLO limits.

