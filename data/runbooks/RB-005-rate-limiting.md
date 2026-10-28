# RB-005: Upstream Traffic Shedding and Rate Limiting Runbook

## Symptoms
- Inbound request volume surging beyond provisioned capacity; queue backlog growing exponentially.

## Action Steps
1. Enable aggressive edge rate limiting at the API gateway for unauthenticated or non-critical traffic.
2. Shed Tier 3 background jobs to protect Tier 1 customer checkout journeys.

