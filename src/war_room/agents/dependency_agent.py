"""Dependency Agent module.

Role: Find which upstream/downstream services, deploys, or blast radiuses are implicated.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, BaseChatClient, tool

from war_room.board import BoardHandle, PostKind
from war_room.environment import Environment
from war_room.tools.dependency_tools import (
    BlastRadiusReport,
    ChangeRecord,
    DependencyMap,
    ServiceHealthReport,
    check_service_health,
    compute_blast_radius,
    get_dependencies,
    get_recent_changes,
)

ROLE = "Dependency Agent"
INSTRUCTIONS = (
    "You are the Dependency Agent. Your single role is to inspect service dependencies, "
    "check the health of upstream and downstream components, retrieve recent software deployments, "
    "compute the blast radius, and publish dependency_finding posts to the Incident Board."
)


def build_dependency_agent(
    client: BaseChatClient,
    board_handle: BoardHandle,
    env: Environment,
) -> Agent:
    """Build and configure the Dependency Agent with typed domain and board tools."""

    @tool
    def tool_get_dependencies(service_name: str) -> dict[str, Any]:
        """Fetch upstream callers and downstream callee services."""
        res: DependencyMap = get_dependencies(env, service_name)
        return res.model_dump()

    @tool
    def tool_check_service_health(service_name: str) -> dict[str, Any]:
        """Inspect error rate, p99 latency, and health state of a service."""
        res: ServiceHealthReport = check_service_health(env, service_name)
        return res.model_dump()

    @tool
    def tool_get_recent_changes(
        service_name: str,
        lookback_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """List deployments and config changes applied to the service within lookback window."""
        res: list[ChangeRecord] = get_recent_changes(env, service_name, lookback_minutes)
        return [item.model_dump() for item in res]

    @tool
    def tool_compute_blast_radius(service_name: str) -> dict[str, Any]:
        """Compute the transitive impact blast radius across the topology."""
        res: BlastRadiusReport = compute_blast_radius(env, service_name)
        return res.model_dump()

    @tool
    async def tool_post_dependency_finding(
        service: str,
        summary: str,
        recent_deploys: list[dict[str, Any]],
        downstream_health: dict[str, str],
        blast_radius_tier1_count: int = 0,
        confidence: float = 0.9,
    ) -> str:
        """Publish verified dependency and topology findings to the Incident Board."""
        post = await board_handle.post(
            kind=PostKind.DEPENDENCY_FINDING,
            summary=summary,
            details={
                "service": service,
                "recent_deploys": recent_deploys,
                "downstream_health": downstream_health,
                "blast_radius_tier1_count": blast_radius_tier1_count,
            },
            confidence=confidence,
        )
        return post.post_id

    @tool
    async def tool_post_tool_failure(
        error_message: str,
        service: str,
    ) -> str:
        """Record a tool failure post on the board if topology queries fail."""
        post = await board_handle.post(
            kind=PostKind.TOOL_FAILURE,
            summary=f"Dependency check failure for {service}: {error_message}",
            details={"error": error_message, "service": service},
        )
        return post.post_id

    tools = [
        tool_get_dependencies,
        tool_check_service_health,
        tool_get_recent_changes,
        tool_compute_blast_radius,
        tool_post_dependency_finding,
        tool_post_tool_failure,
    ]

    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=tools,
        name=ROLE,
    )
