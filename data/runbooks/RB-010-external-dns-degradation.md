# RB-010: External DNS Degradation Runbook

## Symptoms
- Outbound network requests failing with `UnknownHostException` or transient NXDOMAIN.

## Action Steps
1. Verify internal CoreDNS resolution metrics.
2. Flush local resolver cache and point upstream queries to fallback secondary DNS resolver.
