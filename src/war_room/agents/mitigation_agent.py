"""Mitigation Agent module.

Role: Propose ranked mitigations from runbooks, past incident memory, and safety checks.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, BaseChatClient, tool

from war_room.board import BoardHandle, PostKind
from war_room.environment import Environment
from war_room.retrieval import BM25Index
from war_room.tools.mitigation_tools import (
    FailoverReadinessReport,
    PastIncidentMatch,
    RollbackCandidate,
    RunbookMatch,
    check_failover_readiness,
    find_similar_past_incidents,
    get_rollback_candidates,
    search_runbooks,
)

ROLE = "Mitigation Agent"
INSTRUCTIONS = (
    "You are the Mitigation Agent. Your single role is to read board findings, "
    "search operational runbooks and past incidents, verify rollback safety and "
    "failover readiness, and publish ranked mitigation_proposal posts to the Incident Board."
)


def build_mitigation_agent(
    client: BaseChatClient,
    board_handle: BoardHandle,
    env: Environment,
    runbook_index: BM25Index[dict[str, Any]],
    past_incidents_index: BM25Index[dict[str, Any]],
) -> Agent:
    """Build and configure the Mitigation Agent with typed domain and board tools."""

    @tool
    def tool_search_runbooks(query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search operational runbooks by symptom using Okapi BM25."""
        res: list[RunbookMatch] = search_runbooks(runbook_index, query, top_k=top_k)
        return [item.model_dump() for item in res]

    @tool
    def tool_find_similar_past_incidents(symptoms: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search historical incident memory for prior resolutions."""
        res: list[PastIncidentMatch] = find_similar_past_incidents(
            past_incidents_index, symptoms, top_k=top_k
        )
        return [item.model_dump() for item in res]

    @tool
    def tool_get_rollback_candidates(service_name: str) -> list[dict[str, Any]]:
        """Check previous deployment artifacts and verify database migration safety."""
        res: list[RollbackCandidate] = get_rollback_candidates(env, service_name)
        return [item.model_dump() for item in res]

    @tool
    def tool_check_failover_readiness(service_name: str) -> dict[str, Any]:
        """Assess secondary warm standby provider or read-replica readiness."""
        res: FailoverReadinessReport = check_failover_readiness(env, service_name)
        return res.model_dump()

    @tool
    async def tool_post_mitigation_proposal(
        action: str,
        service: str,
        target_version: str | None = None,
        rationale: str = "",
        confidence: float = 0.9,
        evidence_refs: list[str] | None = None,
    ) -> str:
        """Publish a ranked mitigation proposal to the Incident Board."""
        post = await board_handle.post(
            kind=PostKind.MITIGATION_PROPOSAL,
            summary=f"Propose {action} on {service}: {rationale}",
            details={
                "action": action,
                "service": service,
                "target_version": target_version,
                "rationale": rationale,
            },
            evidence_refs=evidence_refs or [],
            confidence=confidence,
        )
        return post.post_id

    tools = [
        tool_search_runbooks,
        tool_find_similar_past_incidents,
        tool_get_rollback_candidates,
        tool_check_failover_readiness,
        tool_post_mitigation_proposal,
    ]

    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=tools,
        name=ROLE,
    )
