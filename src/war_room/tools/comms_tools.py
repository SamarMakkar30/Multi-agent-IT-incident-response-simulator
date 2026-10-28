"""Domain tools for the Comms Agent."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class CommsPolicyCheck(BaseModel):
    """Result of external communications policy compliance check."""

    compliant: bool = Field(description="Whether update satisfies public communications policy")
    violations: list[str] = Field(default_factory=list, description="Policy violations detected")


STATUS_TEMPLATES = {
    "SEV1": (
        "**CRITICAL SERVICE INCIDENT**: We are investigating an issue impacting {service}. "
        "Impact: {user_impact}. Status: {status}. Engineering teams have identified cause "
        "and mitigation actions are in progress. Next update in 15 minutes."
    ),
    "SEV2": (
        "**SERVICE DEGRADATION**: We are observing degraded performance on {service}. "
        "Impact: {user_impact}. Status: {status}. Mitigations have been initiated. "
        "Next update in 30 minutes."
    ),
    "SEV3": (
        "**MINOR SERVICE NOTICE**: Non-critical components of {service} are experiencing latency. "
        "Impact: {user_impact}. Status: {status}. Systems remain operational."
    ),
    "SEV4": (
        "**INFORMATIONAL**: Maintenance or minor telemetry drift on {service}. "
        "No customer degradation detected."
    ),
}

INTERNAL_IP_REGEX = re.compile(
    r"\b(?:10\.\d{1,3}|192\.168\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
)
INTERNAL_EMAIL_REGEX = re.compile(r"\b[\w\.-]+@company\.internal\b", re.IGNORECASE)
STACK_TRACE_REGEX = re.compile(
    r"(?i)(?:traceback \(most recent call last\)|exception in thread|at com\.company)"
)


def get_status_template(severity: str = "SEV1", status_type: str = "IDENTIFIED") -> str:
    """Retrieve standard public incident status communication template."""
    sev_upper = severity.upper()
    return STATUS_TEMPLATES.get(sev_upper, STATUS_TEMPLATES["SEV2"])


def render_status_update(
    template: str,
    service: str,
    status: str,
    user_impact: str,
) -> str:
    """Render customer-facing status-page update text from template."""
    rendered = template.format(
        service=service,
        status=status,
        user_impact=user_impact,
        timestamp=datetime.now(UTC).strftime("%H:%M UTC"),
    )
    return rendered


def check_comms_policy(text: str) -> CommsPolicyCheck:
    """Validate that status text contains zero internal infrastructure IPs, emails, or traces."""
    violations = []

    if INTERNAL_IP_REGEX.search(text):
        violations.append("Contains internal private IP address")

    if INTERNAL_EMAIL_REGEX.search(text):
        violations.append("Contains internal employee email address")

    if STACK_TRACE_REGEX.search(text):
        violations.append("Contains raw stack trace or internal exception dump")

    return CommsPolicyCheck(
        compliant=len(violations) == 0,
        violations=violations,
    )
