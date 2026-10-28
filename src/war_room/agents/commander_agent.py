"""Incident Commander module.

Role: Decide mitigation, record findings, construct postmortem timeline, or escalate.
LEAST PRIVILEGE: Commander has ZERO data-source tools. Decides ONLY from board evidence.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, BaseChatClient, tool

from war_room.board import BoardHandle
from war_room.tools.commander_tools import (
    DecisionResult,
    EscalationResult,
    EvidenceRequestResult,
    EvidenceValidationResult,
    PostSummary,
    TimelineResult,
    build_timeline,
    escalate_to_human,
    read_board,
    record_decision,
    request_evidence,
    validate_evidence,
)

ROLE = "Incident Commander"
INSTRUCTIONS = (
    "You are the Incident Commander. You lead incident resolution under strict least-privilege. "
    "You have no direct access to system logs or infrastructure state. "
    "You read the Incident Board, validate posted evidence, record official decisions with "
    "rationale and rejected alternatives, request missing evidence from specialists, construct "
    "the chronological postmortem timeline, or escalate to human on-call if "
    "confidence is below threshold."
)


def build_commander_agent(
    client: BaseChatClient,
    board_handle: BoardHandle,
) -> Agent:
    """Build and configure the Incident Commander with decision and timeline tools."""

    @tool
    def tool_read_board(filter_kind: str | None = None) -> list[dict[str, Any]]:
        """Read current posts from the Incident Board."""
        res: list[PostSummary] = read_board(board_handle, filter_kind=filter_kind)
        return [item.model_dump() for item in res]

    @tool
    def tool_validate_evidence(
        evidence_refs: list[str],
        chosen_mitigation: str,
        target_service: str,
    ) -> dict[str, Any]:
        """Validate candidate evidence against Evidence Guard rules."""
        res: EvidenceValidationResult = validate_evidence(
            board_handle, evidence_refs, chosen_mitigation, target_service
        )
        return res.model_dump()

    @tool
    async def tool_record_decision(
        likely_cause: str,
        mitigation: str,
        target_service: str,
        rationale: str,
        rejected_alternatives: list[dict[str, str]],
        confidence: float,
        evidence_refs: list[str],
        confidence_threshold: float = 0.55,
    ) -> dict[str, Any]:
        """Record the final incident mitigation decision on the Incident Board."""
        res: DecisionResult = await record_decision(
            board_handle=board_handle,
            likely_cause=likely_cause,
            mitigation=mitigation,
            target_service=target_service,
            rationale=rationale,
            rejected_alternatives=rejected_alternatives,
            confidence=confidence,
            evidence_refs=evidence_refs,
            confidence_threshold=confidence_threshold,
        )
        return res.model_dump()

    @tool
    async def tool_request_evidence(
        target_agent: str,
        query: str,
        missing_aspects: list[str],
    ) -> dict[str, Any]:
        """Request additional evidence from a specialist agent (Logs or Dependency)."""
        res: EvidenceRequestResult = await request_evidence(
            board_handle=board_handle,
            target_agent=target_agent,
            query=query,
            missing_aspects=missing_aspects,
        )
        return res.model_dump()

    @tool
    def tool_build_timeline() -> dict[str, Any]:
        """Construct the chronological postmortem timeline from board posts."""
        res: TimelineResult = build_timeline(board_handle)
        return res.model_dump()

    @tool
    async def tool_escalate_to_human(
        reason: str,
        partial_cause: str,
        evidence_summary: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        """Escalate the incident to human on-call engineers."""
        res: EscalationResult = await escalate_to_human(
            board_handle=board_handle,
            reason=reason,
            partial_cause=partial_cause,
            evidence_summary=evidence_summary,
            evidence_refs=evidence_refs,
        )
        return res.model_dump()

    tools = [
        tool_read_board,
        tool_validate_evidence,
        tool_record_decision,
        tool_request_evidence,
        tool_build_timeline,
        tool_escalate_to_human,
    ]

    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=tools,
        name=ROLE,
    )
