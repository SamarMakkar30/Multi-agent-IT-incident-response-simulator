"""Domain tools for the Dependency Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from war_room.environment import Environment


class DependencyMap(BaseModel):
    """Direct upstream and downstream connections for a service."""

    service: str = Field(description="Target service")
    upstreams: list[str] = Field(description="Services that call this service")
    downstreams: list[str] = Field(description="Services that this service calls")


class ServiceHealthReport(BaseModel):
    """Current health and telemetry status of a service."""

    service: str = Field(description="Service name")
    health_status: str = Field(description="Health condition (HEALTHY, DEGRADED, DOWN)")
    http_error_rate_5xx: float = Field(description="Observed 5xx error rate")
    p99_latency_ms: float = Field(description="P99 latency in milliseconds")
    container_restarts: int = Field(description="Number of container restart events")
    provider_statuses: dict[str, Any] = Field(
        default_factory=dict, description="External provider health status if applicable"
    )


class ChangeRecord(BaseModel):
    """Record of a recent software release or configuration change."""

    service: str = Field(description="Affected service")
    version: str = Field(description="Deployed release version")
    deployed_at: str = Field(description="Timestamp of release")
    commit: str = Field(description="Git commit SHA")
    breaking_db_migration: bool = Field(
        description="Whether release included destructive DB schema changes"
    )
    changelog: str = Field(description="Summary of release contents")


class BlastRadiusReport(BaseModel):
    """Computed downstream and upstream impact across the service topology."""

    failing_service: str = Field(description="Primary service with anomaly")
    impacted_services: list[str] = Field(description="Transitively impacted upstream dependencies")
    impacted_tier1_count: int = Field(description="Number of Tier 1 core services impacted")
    user_facing_impacted: bool = Field(
        description="Whether any public customer entrypoints are degraded"
    )


def get_dependencies(env: Environment, service_name: str) -> DependencyMap:
    """Retrieve upstream caller services and downstream dependency services."""
    deps = env.get_dependencies(service_name)
    return DependencyMap(
        service=service_name,
        upstreams=deps.get("upstreams", []),
        downstreams=deps.get("downstreams", []),
    )


def check_service_health(env: Environment, service_name: str) -> ServiceHealthReport:
    """Inspect current runtime telemetry, error budget, and provider health."""
    metrics_data = env.get_metrics(service_name)
    if not metrics_data:
        return ServiceHealthReport(
            service=service_name,
            health_status="UNKNOWN",
            http_error_rate_5xx=0.0,
            p99_latency_ms=0.0,
            container_restarts=0,
            provider_statuses={},
        )

    metrics = metrics_data.get("metrics", {})
    return ServiceHealthReport(
        service=service_name,
        health_status=str(metrics_data.get("health_status", "HEALTHY")),
        http_error_rate_5xx=float(metrics.get("http_error_rate_5xx", 0.0)),
        p99_latency_ms=float(metrics.get("p99_latency_ms", 0.0)),
        container_restarts=int(metrics.get("container_restarts", 0)),
        provider_statuses=metrics_data.get("providers", {}),
    )


def get_recent_changes(
    env: Environment,
    service_name: str,
    lookback_minutes: int = 60,
) -> list[ChangeRecord]:
    """Retrieve software deployments occurring within the lookback window."""
    deploys = env.get_deploys(service_name=service_name, lookback_minutes=lookback_minutes)
    records = []
    for d in deploys:
        records.append(
            ChangeRecord(
                service=d.get("service", service_name),
                version=d.get("version", "unknown"),
                deployed_at=d.get("deployed_at", ""),
                commit=d.get("commit", ""),
                breaking_db_migration=bool(d.get("breaking_db_migration", False)),
                changelog=d.get("changelog", ""),
            )
        )
    return records


def compute_blast_radius(env: Environment, service_name: str) -> BlastRadiusReport:
    """Compute the cascade blast radius by traversing upstream callers."""
    visited = set()
    queue = [service_name]

    while queue:
        current = queue.pop(0)
        deps = env.get_dependencies(current)
        for up in deps.get("upstreams", []):
            if up not in visited and up != service_name:
                visited.add(up)
                queue.append(up)

    impacted = sorted(visited)
    tier1_count = 0
    user_facing = False

    for s in impacted + [service_name]:
        meta = env.get_service_metadata(s)
        if meta:
            if meta.get("tier") == 1:
                tier1_count += 1
            if meta.get("user_facing"):
                user_facing = True

    return BlastRadiusReport(
        failing_service=service_name,
        impacted_services=impacted,
        impacted_tier1_count=tier1_count,
        user_facing_impacted=user_facing,
    )
