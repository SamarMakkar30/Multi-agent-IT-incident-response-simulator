# RB-004: Database Connection Pool Exhaustion Runbook

## Symptoms
- Applications reporting `ConnectionTimeoutException` or `PoolExhaustedException`.
- Database server CPU is moderate, but client connections have reached maximum pool size.

## Action Steps
1. Identify leaking transactions or unclosed connections in slow queries.
2. Temporarily increase pool ceiling if DB server capacity allows.
3. Perform graceful rolling restart of application pods holding stale connections.
