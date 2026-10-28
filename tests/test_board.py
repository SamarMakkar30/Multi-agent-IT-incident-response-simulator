"""Unit tests for Incident Board (Blackboard)."""

import asyncio
from datetime import UTC, datetime

import pytest

from war_room.board import IncidentBoard, PermissionError, PostKind


@pytest.fixture
def board():
    def clock():
        return datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

    return IncidentBoard(incident_id="INC-1001", clock=clock)


@pytest.mark.asyncio
async def test_board_append_only_and_sequence(board):
    handle = board.get_handle("Alert Agent")
    p1 = await handle.post(
        kind=PostKind.INCIDENT_SIGNAL,
        summary="High 5xx error rate",
        details={"service": "checkout-service"},
    )
    assert p1.post_id == "P-001"
    assert p1.seq == 1
    assert p1.author == "Alert Agent"

    p2 = await handle.post(
        kind=PostKind.INCIDENT_SIGNAL,
        summary="Latency degradation",
    )
    assert p2.post_id == "P-002"
    assert p2.seq == 2

    assert len(board.read_all()) == 2
    assert board.get_post("P-001") == p1
    assert board.get_post("P-002") == p2
    assert board.get_post("P-999") is None


@pytest.mark.asyncio
async def test_permission_matrix_enforcement(board):
    alert_handle = board.get_handle("Alert Agent")
    logs_handle = board.get_handle("Logs Agent")
    commander_handle = board.get_handle("Incident Commander")

    # Alert Agent can post incident_signal
    await alert_handle.post(kind=PostKind.INCIDENT_SIGNAL, summary="Alert triggered")

    # Alert Agent CANNOT post decision
    with pytest.raises(PermissionError, match="not permitted to post decision"):
        await alert_handle.post(kind=PostKind.DECISION, summary="Unauthorized decision")

    # Logs Agent can post log_finding and tool_failure
    await logs_handle.post(kind=PostKind.LOG_FINDING, summary="Found 500 error spike")
    await logs_handle.post(kind=PostKind.TOOL_FAILURE, summary="Log query timeout")

    # Logs Agent CANNOT post mitigation_proposal
    with pytest.raises(PermissionError, match="not permitted to post mitigation_proposal"):
        await logs_handle.post(kind=PostKind.MITIGATION_PROPOSAL, summary="Rollback now")

    # Commander can post decision, escalation, evidence_request, timeline_entry
    await commander_handle.post(kind=PostKind.EVIDENCE_REQUEST, summary="Need more logs")
    await commander_handle.post(kind=PostKind.DECISION, summary="Rollback approved")

    # Any agent can post security_note
    await alert_handle.post(kind=PostKind.SECURITY_NOTE, summary="Suspicious payload detected")
    await logs_handle.post(kind=PostKind.SECURITY_NOTE, summary="Injection pattern caught")


@pytest.mark.asyncio
async def test_author_binding(board):
    handle = board.get_handle("Dependency Agent")
    assert handle.author == "Dependency Agent"

    post = await handle.post(kind=PostKind.DEPENDENCY_FINDING, summary="Upstream gateway OK")
    assert post.author == "Dependency Agent"


@pytest.mark.asyncio
async def test_concurrent_monotonic_writes(board):
    logs_handle = board.get_handle("Logs Agent")
    dep_handle = board.get_handle("Dependency Agent")

    # Run 50 concurrent posts from alternating agents
    async def post_log(i: int):
        return await logs_handle.post(kind=PostKind.LOG_FINDING, summary=f"Log item {i}")

    async def post_dep(i: int):
        return await dep_handle.post(kind=PostKind.DEPENDENCY_FINDING, summary=f"Dep item {i}")

    tasks = []
    for i in range(25):
        tasks.append(post_log(i))
        tasks.append(post_dep(i))

    results = await asyncio.gather(*tasks)

    assert len(results) == 50
    posts = board.read_all()
    assert len(posts) == 50

    # Ensure strictly monotonic sequence numbers 1..50
    seqs = [p.seq for p in posts]
    assert seqs == list(range(1, 51))

    # Ensure post_ids match P-001..P-050
    post_ids = [p.post_id for p in posts]
    assert post_ids == [f"P-{i:03d}" for i in range(1, 51)]
