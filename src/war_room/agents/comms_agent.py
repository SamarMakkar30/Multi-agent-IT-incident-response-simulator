"""Comms Agent module.

Role: Draft and validate public status-page updates according to communication policy.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, BaseChatClient, tool

from war_room.board import BoardHandle, PostKind
from war_room.tools.comms_tools import (
    CommsPolicyCheck,
    check_comms_policy,
    get_status_template,
    render_status_update,
)

ROLE = "Comms Agent"
INSTRUCTIONS = (
    "You are the Comms Agent. Your single role is to read the official decision from the board, "
    "select the appropriate status template, render a customer-facing status update, "
    "enforce communications policy (no internal IPs, emails, or stack traces), "
    "and publish the status_update to the Incident Board."
)


def build_comms_agent(
    client: BaseChatClient,
    board_handle: BoardHandle,
) -> Agent:
    """Build and configure the Comms Agent with template and policy tools."""

    @tool
    def tool_get_status_template(severity: str, status_type: str = "IDENTIFIED") -> str:
        """Select a standard status update template for the given severity."""
        return get_status_template(severity=severity, status_type=status_type)

    @tool
    def tool_render_status_update(
        template: str,
        service: str,
        status: str,
        user_impact: str,
    ) -> str:
        """Render public-facing markdown text from template."""
        return render_status_update(template, service, status, user_impact)

    @tool
    def tool_check_comms_policy(text: str) -> dict[str, Any]:
        """Verify that rendered text contains no internal IPs, employee emails, or stack traces."""
        res: CommsPolicyCheck = check_comms_policy(text)
        return res.model_dump()

    @tool
    async def tool_post_status_update(
        service: str,
        status_text: str,
        policy_compliant: bool,
    ) -> str:
        """Publish the verified status update to the Incident Board."""
        post = await board_handle.post(
            kind=PostKind.STATUS_UPDATE,
            summary=f"Status update published for {service}",
            details={"service": service, "status_text": status_text, "compliant": policy_compliant},
        )
        return post.post_id

    tools = [
        tool_get_status_template,
        tool_render_status_update,
        tool_check_comms_policy,
        tool_post_status_update,
    ]

    return Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=tools,
        name=ROLE,
    )
