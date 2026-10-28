"""Alert Agent module.

Role: Normalise the raw alert into an incident signal and set deterministic severity.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, BaseChatClient, tool

from war_room.board import BoardHandle, PostKind
from war_room.environment import Environment
from war_room.tools.alert_tools import (
    AlertSignal,
    ServiceMetadata,
    SeverityScore,
    get_service_metadata,
    parse_alert,
    score_severity,
)

ROLE = "Alert Agent"
INSTRUCTIONS = (
    "You are the Alert Agent. Your single role is to normalize incoming alert payloads, "
    "query service metadata from the topology, compute a deterministic SEV1-SEV4 severity score, "
    "and publish an incident_signal to the Incident Board."
)


def build_alert_agent(
    client: BaseChatClient,
    board_handle: BoardHandle,
    env: Environment,
) -> Agent:
    """Build and configure the Alert Agent with typed domain and board tools."""

    @tool
    def tool_parse_alert(raw_alert: dict[str, Any]) -> dict[str, Any]:
        """Normalize raw alert payload and sanitize untrusted input."""
        res: AlertSignal = parse_alert(raw_alert)
        return res.model_dump()

    @tool
    def tool_score_severity(
        tier: int,
        metric_name: str,
        breach_ratio: float,
        is_user_facing: bool,
    ) -> dict[str, Any]:
        """Score incident severity deterministically (SEV1-SEV4)."""
        res: SeverityScore = score_severity(tier, metric_name, breach_ratio, is_user_facing)
        return res.model_dump()

    @tool
    def tool_get_service_metadata(service_name: str) -> dict[str, Any]:
        """Fetch tier, ownership, and SLO for the target service."""
        res: ServiceMetadata = get_service_metadata(env, service_name)
        return res.model_dump()

    @tool
    async def tool_post_incident_signal(
        service: str,
        metric: str,
        severity: str,
        summary: str,
        details: dict[str, Any],
        untrusted_flags: list[str] | None = None,
    ) -> str:
        """Publish the normalized incident_signal post to the shared blackboard."""
        post = await board_handle.post(
            kind=PostKind.INCIDENT_SIGNAL,
            summary=summary,
            details={
                "service": service,
                "metric": metric,
                "severity": severity,
                **details,
            },
            untrusted_flags=untrusted_flags or [],
        )
        return post.post_id

    tools = [
        tool_parse_alert,
        tool_score_severity,
        tool_get_service_metadata,
        tool_post_incident_signal,
    ]

    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=tools,
        name=ROLE,
    )
