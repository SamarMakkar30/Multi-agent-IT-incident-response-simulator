# RB-002: Memory Leak and OOMKilled Service Restart Runbook

## Symptoms
- Service pod/container restarts with exit code 137 (OOMKilled).
- Monotonic linear increase in heap memory or resident set size (RSS) over time without stabilizing after garbage collection.
- No recent deployment in the last 24 hours.
- Increasing tail latency (p99) due to frequent full GC pauses before crash.

## Action Steps
1. Perform a staggered rolling restart of the service pods to immediately reclaim memory without dropping in-flight traffic.
2. Verify heap usage drops back to baseline post-restart.
3. Capture a heap dump from one dying pod if possible for offline analysis.
4. Open a high-priority bug ticket for the service owner to investigate the unbounded memory accumulation.
