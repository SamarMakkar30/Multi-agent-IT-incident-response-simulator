"""Deterministic safety guards, prompt-injection defense, and evidence verification."""

from __future__ import annotations

import re
from typing import Any

from war_room.board import IncidentBoard, PostKind

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+(?:instructions|prompts)",
    r"you\s+are\s+now\s+in",
    r"system\s+override",
    r"mark\s+(?:the\s+)?(?:incident\s+)?resolved",
    r"delete\s+logs",
    r"disregard\s+(?:all\s+)?prior",
    r"bypass\s+security",
]

COMPILED_INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def sanitize_untrusted_input(text: str) -> tuple[str, list[str]]:
    """Scan untrusted data for adversarial instruction injection attempts.

    Returns:
        (sanitized_text, untrusted_flags)
    """
    matches = COMPILED_INJECTION_REGEX.findall(text)
    if not matches:
        return text, []

    flags = ["prompt_injection_detected"]

    def _replace_match(_match: re.Match[str]) -> str:
        return "[QUARANTINED_UNTRUSTED_CONTENT: <REDACTED_ADVERSARIAL_INSTRUCTION>]"

    sanitized = COMPILED_INJECTION_REGEX.sub(_replace_match, text)
    return sanitized, flags


def validate_decision_evidence(
    board: IncidentBoard,
    evidence_refs: list[str],
    chosen_mitigation: str,
    target_service: str,
    allow_deviation: bool = False,
) -> tuple[bool, str | None]:
    """Enforce Evidence Guard constraints on Incident Commander decisions.

    Rules:
    1. At least 1 evidence ref provided.
    2. Every referenced post_id MUST exist on the board.
    3. At least 2 evidence posts from at least 2 distinct author agents.
    4. Chosen mitigation must match a posted proposal (unless human escalation or deviation).
    """
    if not evidence_refs:
        return False, "Evidence guard violation: No evidence post IDs provided."

    # Rule 2: Every referenced post_id must exist
    found_posts = []
    for ref in evidence_refs:
        post = board.get_post(ref)
        if not post:
            return False, f"Evidence guard violation: Referenced post ID '{ref}' not on board."
        found_posts.append(post)

    # Rule 3: At least 2 distinct author agents
    authors = {p.author for p in found_posts}
    if len(authors) < 2:
        return (
            False,
            f"Evidence guard violation: Requires evidence from >= 2 distinct authors, "
            f"found only: {list(authors)}",
        )

    # Rule 4: Chosen mitigation must match an existing proposal
    if chosen_mitigation != "escalate_to_human" and not allow_deviation:
        proposals = board.read_by_kind(PostKind.MITIGATION_PROPOSAL)
        matching_proposals = []
        for prop in proposals:
            details = prop.details if isinstance(prop.details, dict) else {}
            prop_action = details.get("action", "") or prop.summary.lower()
            prop_service = details.get("service", "")
            if chosen_mitigation.lower() in prop_action.lower():
                if not prop_service or target_service.lower() in prop_service.lower():
                    matching_proposals.append(prop)

        if not matching_proposals:
            return (
                False,
                f"Evidence guard violation: Mitigation '{chosen_mitigation}' does not match "
                f"any posted mitigation_proposal on the board.",
            )

    return True, None


def check_confidence_gate(
    confidence: float,
    threshold: float = 0.55,
) -> tuple[bool, str | None]:
    """Enforce Confidence Gate: confidence below threshold forces human escalation."""
    if confidence < threshold:
        return (
            False,
            f"Confidence gate triggered: Confidence {confidence:.2f} is below "
            f"threshold {threshold:.2f}. "
            f"Automated mitigation blocked; must escalate to human on-call.",
        )
    return True, None


class ToolExecutionGuard:
    """Manages tool call timeouts, retry bounds, and failure containment."""

    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max_retries

    def record_tool_failure(
        self,
        tool_name: str,
        error_message: str,
        service: str = "unknown",
    ) -> dict[str, Any]:
        """Wrap tool failure into structured failure diagnostics for board posting."""
        return {
            "tool": tool_name,
            "service": service,
            "status": "failed",
            "error": error_message,
            "missing_evidence": f"Unable to retrieve telemetry from {tool_name} for {service}",
        }
