"""Unit tests for Incident Commander domain tools."""

import pytest

from war_room.board import IncidentBoard, PostKind
from war_room.tools.commander_tools import (
    build_timeline,
    escalate_to_human,
    read_board,
    record_decision,
    request_evidence,
    validate_evidence,
)


@pytest.fixture
def board():
    return IncidentBoard(incident_id="INC-COMM-001")


@pytest.mark.asyncio
async def test_commander_tools_decision_flow(board: IncidentBoard):
    commander_handle = board.get_handle("Incident Commander")
    logs_handle = board.get_handle("Logs Agent")
    dep_handle = board.get_handle("Dependency Agent")
    mit_handle = board.get_handle("Mitigation Agent")

    # Specialist agents post evidence
    p1 = await logs_handle.post(
        kind=PostKind.LOG_FINDING, summary="NullPointerException in CheckoutController"
    )
    p2 = await dep_handle.post(
        kind=PostKind.DEPENDENCY_FINDING, summary="Deploy v2.14.0 found 15 mins ago"
    )
    await mit_handle.post(
        kind=PostKind.MITIGATION_PROPOSAL,
        summary="Rollback checkout-service to v2.13.4",
        details={"action": "rollback", "service": "checkout-service", "target_version": "v2.13.4"},
    )

    # 1. read_board
    summaries = read_board(commander_handle)
    assert len(summaries) == 3

    # 2. validate_evidence
    val = validate_evidence(
        commander_handle, [p1.post_id, p2.post_id], "rollback", "checkout-service"
    )
    assert val.valid is True
    assert set(val.authors) == {"Logs Agent", "Dependency Agent"}

    # 3. record_decision
    dec = await record_decision(
        board_handle=commander_handle,
        likely_cause="Deploy regression in v2.14.0",
        mitigation="rollback",
        target_service="checkout-service",
        rationale="Error onset immediately followed deploy of v2.14.0",
        rejected_alternatives=[
            {"mitigation": "restart", "reason": "Code bug requires code rollback"}
        ],
        confidence=0.92,
        evidence_refs=[p1.post_id, p2.post_id],
    )
    assert dec.success is True
    assert dec.post_id is not None
    assert dec.decision["mitigation"] == "rollback"

    # 4. build_timeline
    timeline = build_timeline(commander_handle)
    assert len(timeline.rows) == 4
    assert "| Incident Time |" in timeline.markdown_table
    assert p1.post_id in timeline.markdown_table


@pytest.mark.asyncio
async def test_commander_evidence_request_and_escalate(board: IncidentBoard):
    commander_handle = board.get_handle("Incident Commander")

    # Request evidence
    req = await request_evidence(
        board_handle=commander_handle,
        target_agent="Logs Agent",
        query="Verify if error rate is increasing",
        missing_aspects=["onset_timestamp"],
    )
    assert req.post_id == "P-001"

    # Escalate to human
    esc = await escalate_to_human(
        board_handle=commander_handle,
        reason="Sparse logs and ambiguous dependencies",
        partial_cause="Unknown",
        evidence_summary="Only 1 warning line detected",
        evidence_refs=["P-001"],
    )
    assert esc.post_id == "P-002"
    assert "Sparse logs" in esc.reason
