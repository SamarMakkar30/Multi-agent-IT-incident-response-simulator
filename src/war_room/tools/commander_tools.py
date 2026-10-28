"""Domain tools for the Incident Commander.

STRUCTURAL LEAST-PRIVILEGE: Commander has ZERO data-source tools.
It decides and coordinates ONLY through the Incident Board.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from war_room.board import BoardHandle, Post, PostKind
from war_room.guards import check_confidence_gate, validate_decision_evidence


class PostSummary(BaseModel):
    """Concise representation of a post on the board."""

    post_id: str
    seq: int
    author: str
    kind: str
    summary: str
    confidence: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class EvidenceValidationResult(BaseModel):
    """Result of validating decision evidence against board posts."""

    valid: bool
    error: str | None = None
    authors: list[str] = Field(default_factory=list)


class DecisionResult(BaseModel):
    """Result of recording an official incident decision."""

    success: bool
    post_id: str | None = None
    decision: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class EvidenceRequestResult(BaseModel):
    """Result of requesting additional evidence from specialist agents."""

    post_id: str
    target_agent: str
    query: str


class TimelineRow(BaseModel):
    """Single row in the postmortem chronological timeline."""

    incident_time: str = Field(description="When it happened in the target system")
    war_room_time: str = Field(description="When an agent posted it to the board")
    author: str = Field(description="Agent role")
    event: str = Field(description="Event summary")
    post_id: str = Field(description="Board post identifier")


class TimelineResult(BaseModel):
    """Chronological postmortem timeline."""

    rows: list[TimelineRow]
    markdown_table: str


class EscalationResult(BaseModel):
    """Outcome of human escalation."""

    post_id: str
    reason: str
    partial_cause: str
    evidence_summary: str


def read_board(
    board_handle: BoardHandle,
    filter_kind: str | None = None,
) -> list[PostSummary]:
    """Read all posts on the Incident Board, optionally filtered by kind."""
    if filter_kind:
        posts = board_handle.read_by_kind(filter_kind)
    else:
        posts = board_handle.read_all()

    summaries = []
    for p in posts:
        summaries.append(
            PostSummary(
                post_id=p.post_id,
                seq=p.seq,
                author=p.author,
                kind=p.kind.value,
                summary=p.summary,
                confidence=p.confidence,
                evidence_refs=p.evidence_refs,
            )
        )
    return summaries


def validate_evidence(
    board_handle: BoardHandle,
    evidence_refs: list[str],
    chosen_mitigation: str,
    target_service: str,
) -> EvidenceValidationResult:
    """Validate that candidate evidence meets all Evidence Guard constraints."""
    valid, err = validate_decision_evidence(
        board=board_handle._board,
        evidence_refs=evidence_refs,
        chosen_mitigation=chosen_mitigation,
        target_service=target_service,
    )
    posts = [board_handle.get_post(r) for r in evidence_refs if board_handle.get_post(r)]
    authors = sorted({p.author for p in posts if p})
    return EvidenceValidationResult(valid=valid, error=err, authors=authors)


async def record_decision(
    board_handle: BoardHandle,
    likely_cause: str,
    mitigation: str,
    target_service: str,
    rationale: str,
    rejected_alternatives: list[dict[str, str]],
    confidence: float,
    evidence_refs: list[str],
    confidence_threshold: float = 0.55,
) -> DecisionResult:
    """Record the final incident decision on the board after validating guards."""
    # 1. Evidence Guard Check
    valid_ev, ev_err = validate_decision_evidence(
        board=board_handle._board,
        evidence_refs=evidence_refs,
        chosen_mitigation=mitigation,
        target_service=target_service,
    )
    if not valid_ev:
        return DecisionResult(
            success=False,
            error=f"Decision blocked by Evidence Guard: {ev_err}",
        )

    # 2. Confidence Gate Check
    passed_conf, conf_err = check_confidence_gate(confidence, threshold=confidence_threshold)
    if not passed_conf:
        # Route to escalation instead
        esc_post = await board_handle.post(
            kind=PostKind.ESCALATION,
            summary=f"Automated mitigation aborted: {conf_err}",
            details={
                "reason": "Confidence below threshold",
                "confidence": confidence,
                "partial_cause": likely_cause,
                "proposed_mitigation": mitigation,
                "evidence_refs": evidence_refs,
            },
            evidence_refs=evidence_refs,
            confidence=confidence,
        )
        return DecisionResult(
            success=False,
            post_id=esc_post.post_id,
            error=conf_err,
        )

    details = {
        "likely_cause": likely_cause,
        "mitigation": mitigation,
        "target_service": target_service,
        "rationale": rationale,
        "rejected_alternatives": rejected_alternatives,
        "confidence": confidence,
        "evidence_refs": evidence_refs,
    }

    summary_text = f"Decided mitigation '{mitigation}' for {target_service}: {likely_cause}"
    post = await board_handle.post(
        kind=PostKind.DECISION,
        summary=summary_text,
        details=details,
        evidence_refs=evidence_refs,
        confidence=confidence,
    )

    return DecisionResult(
        success=True,
        post_id=post.post_id,
        decision=details,
    )


async def request_evidence(
    board_handle: BoardHandle,
    target_agent: str,
    query: str,
    missing_aspects: list[str],
) -> EvidenceRequestResult:
    """Publish an evidence request on the board to reactivate specialist agents."""
    details = {
        "target_agent": target_agent,
        "query": query,
        "missing_aspects": missing_aspects,
    }
    summary_text = f"Evidence requested from {target_agent}: {query}"
    post = await board_handle.post(
        kind=PostKind.EVIDENCE_REQUEST,
        summary=summary_text,
        details=details,
    )
    return EvidenceRequestResult(
        post_id=post.post_id,
        target_agent=target_agent,
        query=query,
    )


def build_timeline(board_handle: BoardHandle) -> TimelineResult:
    """Construct deterministic postmortem chronological timeline table from board posts."""
    posts: list[Post] = board_handle.read_all()
    rows: list[TimelineRow] = []

    for p in posts:
        # Determine incident system time
        inc_time_str = "N/A"
        if p.incident_time:
            inc_time_str = p.incident_time.isoformat()
        elif isinstance(p.details, dict) and "incident_time" in p.details:
            inc_time_str = str(p.details["incident_time"])
        elif isinstance(p.details, dict) and "triggered_at" in p.details:
            inc_time_str = str(p.details["triggered_at"])
        elif isinstance(p.details, dict) and "onset_timestamp" in p.details:
            inc_time_str = str(p.details["onset_timestamp"])
        elif isinstance(p.details, dict) and "deployed_at" in p.details:
            inc_time_str = str(p.details["deployed_at"])

        war_room_time_str = p.posted_at.isoformat()

        rows.append(
            TimelineRow(
                incident_time=inc_time_str,
                war_room_time=war_room_time_str,
                author=p.author,
                event=p.summary,
                post_id=p.post_id,
            )
        )

    # Format Markdown table
    header = "| Incident Time | War Room Time | Author | Event | Post ID |\n"
    divider = "| --- | --- | --- | --- | --- |\n"
    body = "".join(
        f"| {r.incident_time} | {r.war_room_time} | {r.author} | {r.event} | {r.post_id} |\n"
        for r in rows
    )
    table_md = header + divider + body

    return TimelineResult(rows=rows, markdown_table=table_md)


async def escalate_to_human(
    board_handle: BoardHandle,
    reason: str,
    partial_cause: str,
    evidence_summary: str,
    evidence_refs: list[str],
) -> EscalationResult:
    """Escalate incident to human on-call when automated confidence is insufficient."""
    details = {
        "reason": reason,
        "partial_cause": partial_cause,
        "evidence_summary": evidence_summary,
        "evidence_refs": evidence_refs,
    }
    post = await board_handle.post(
        kind=PostKind.ESCALATION,
        summary=f"Incident escalated to human on-call: {reason}",
        details=details,
        evidence_refs=evidence_refs,
    )
    return EscalationResult(
        post_id=post.post_id,
        reason=reason,
        partial_cause=partial_cause,
        evidence_summary=evidence_summary,
    )
