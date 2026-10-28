"""Logs Agent module.

Role: Find what the logs say about the affected service, signatures, and error onset.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, BaseChatClient, tool

from war_room.board import BoardHandle, PostKind
from war_room.environment import Environment
from war_room.tools.logs_tools import (
    ErrorOnsetInfo,
    ErrorSignatureSummary,
    LogSearchResult,
    find_error_onset,
    search_logs,
    summarize_error_signatures,
)

ROLE = "Logs Agent"
INSTRUCTIONS = (
    "You are the Logs Agent. Your single role is to search application logs, "
    "cluster error signatures, pinpoint error onset timestamps, and publish "
    "log_finding posts to the Incident Board."
)


def build_logs_agent(
    client: BaseChatClient,
    board_handle: BoardHandle,
    env: Environment,
) -> Agent:
    """Build and configure the Logs Agent with typed domain and board tools."""

    @tool
    def tool_search_logs(
        service_name: str,
        query: str = "",
        time_window_minutes: int = 30,
    ) -> dict[str, Any]:
        """Search application logs for occurrences of errors or keywords."""
        res: LogSearchResult = search_logs(env, service_name, query, time_window_minutes)
        return res.model_dump()

    @tool
    def tool_summarize_error_signatures(
        service_name: str,
        time_window_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Cluster and count unique error signatures for the service."""
        res: list[ErrorSignatureSummary] = summarize_error_signatures(
            env, service_name, time_window_minutes
        )
        return [item.model_dump() for item in res]

    @tool
    def tool_find_error_onset(
        service_name: str,
        error_signature: str,
    ) -> dict[str, Any]:
        """Determine the exact timestamp when an error condition first emerged."""
        res: ErrorOnsetInfo = find_error_onset(env, service_name, error_signature)
        return res.model_dump()

    @tool
    async def tool_post_log_finding(
        service: str,
        summary: str,
        error_signatures: list[str],
        onset_timestamp: str | None = None,
        confidence: float = 0.9,
        untrusted_flags: list[str] | None = None,
    ) -> str:
        """Publish a verified log finding to the Incident Board."""
        post = await board_handle.post(
            kind=PostKind.LOG_FINDING,
            summary=summary,
            details={
                "service": service,
                "error_signatures": error_signatures,
                "onset_timestamp": onset_timestamp,
            },
            confidence=confidence,
            untrusted_flags=untrusted_flags or [],
        )
        return post.post_id

    @tool
    async def tool_post_tool_failure(
        error_message: str,
        service: str,
    ) -> str:
        """Record a tool failure post on the board if logs are inaccessible or timed out."""
        post = await board_handle.post(
            kind=PostKind.TOOL_FAILURE,
            summary=f"Logs query failure for {service}: {error_message}",
            details={"error": error_message, "service": service},
        )
        return post.post_id

    tools = [
        tool_search_logs,
        tool_summarize_error_signatures,
        tool_find_error_onset,
        tool_post_log_finding,
        tool_post_tool_failure,
    ]

    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=tools,
        name=ROLE,
    )
