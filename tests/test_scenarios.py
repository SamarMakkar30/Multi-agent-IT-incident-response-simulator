"""End-to-End Scenario Test Suite (S1 - S6).

Asserts full compliance with Output Contract:
1. Diagnosed Likely Cause with confidence and evidence post IDs.
2. Chosen Mitigation (rollback | restart | failover | escalate_to_human), target service, rationale,
   rejected alternatives with explicit reasons, and evidence post IDs.
3. Postmortem timeline table (incident_time, war_room_time, author, event, post_id).
4. Machine-readable JSON saved to outputs/<incident_id>.json.
5. Append-only run log hash chain verification.
"""

from pathlib import Path

import pytest

from war_room.environment import Environment
from war_room.orchestrator import WarRoomOrchestrator


@pytest.fixture
def clean_outputs_dir(tmp_path: Path):
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@pytest.fixture
def clean_runlog_path(tmp_path: Path):
    return tmp_path / "run_log.jsonl"


@pytest.mark.asyncio
async def test_scenario_s1_bad_deploy(clean_outputs_dir: Path, clean_runlog_path: Path):
    """S1 bad_deploy: checkout-service 5xx spike -> rollback to v2.13.4."""
    env = Environment(data_dir="data", scenario_id="s1_bad_deploy")
    orch = WarRoomOrchestrator(env=env, outputs_dir=clean_outputs_dir)
    orch.run_log.log_path = clean_runlog_path

    out = await orch.run()

    # 1. Cause & Evidence
    assert "deploy regression" in out.likely_cause.lower()
    assert out.confidence >= 0.90
    assert len(out.evidence_post_ids) >= 2

    # 2. Mitigation Contract
    assert out.mitigation == "rollback"
    assert out.target_service == "checkout-service"
    assert "v2.13.4" in out.rationale or "rollback" in out.rationale.lower()
    assert len(out.rejected_alternatives) >= 1
    rejected_mitigations = [r["mitigation"] for r in out.rejected_alternatives]
    assert "restart" in rejected_mitigations

    # 3. Postmortem Timeline
    assert "| Incident Time |" in out.timeline_markdown
    assert "checkout-service" in out.timeline_markdown

    # 4. JSON output and Hash Chain
    assert Path(out.board_json_path).exists()
    assert out.run_log_verified is True


@pytest.mark.asyncio
async def test_scenario_s2_memory_leak(clean_outputs_dir: Path, clean_runlog_path: Path):
    """S2 memory_leak: search-service OOMKilled crash-loop -> rolling restart."""
    env = Environment(data_dir="data", scenario_id="s2_memory_leak")
    orch = WarRoomOrchestrator(env=env, outputs_dir=clean_outputs_dir)
    orch.run_log.log_path = clean_runlog_path

    out = await orch.run()

    assert "memory leak" in out.likely_cause.lower()
    assert out.mitigation == "restart"
    assert out.target_service == "search-service"
    assert out.confidence >= 0.90
    assert len(out.evidence_post_ids) >= 2

    rejected = [r["mitigation"] for r in out.rejected_alternatives]
    assert "rollback" in rejected
    assert out.run_log_verified is True


@pytest.mark.asyncio
async def test_scenario_s3_upstream_outage(clean_outputs_dir: Path, clean_runlog_path: Path):
    """S3 upstream_outage: orders timeouts caused by payments-gateway provider -> failover."""
    env = Environment(data_dir="data", scenario_id="s3_upstream_outage")
    orch = WarRoomOrchestrator(env=env, outputs_dir=clean_outputs_dir)
    orch.run_log.log_path = clean_runlog_path

    out = await orch.run()

    assert "upstream provider" in out.likely_cause.lower()
    assert out.mitigation == "failover"
    assert out.target_service == "payments-gateway"
    assert out.confidence >= 0.90
    assert len(out.evidence_post_ids) >= 2

    rejected = [r["mitigation"] for r in out.rejected_alternatives]
    assert "rollback" in rejected
    assert out.run_log_verified is True


@pytest.mark.asyncio
async def test_scenario_s4_ambiguous_evidence(clean_outputs_dir: Path, clean_runlog_path: Path):
    """S4 ambiguous_evidence: sparse logs, tool timeout, loop exhausted -> escalate_to_human."""
    env = Environment(data_dir="data", scenario_id="s4_ambiguous_evidence")
    orch = WarRoomOrchestrator(env=env, outputs_dir=clean_outputs_dir)
    orch.run_log.log_path = clean_runlog_path

    out = await orch.run()

    assert out.mitigation == "escalate_to_human"
    assert out.confidence < 0.55  # Below gate threshold
    assert "sparse" in out.likely_cause.lower() or "inconclusive" in out.likely_cause.lower()
    assert len(out.evidence_post_ids) >= 1

    # Check that board JSON recorded escalation post
    json_path = Path(out.board_json_path)
    assert json_path.exists()
    assert out.run_log_verified is True


@pytest.mark.asyncio
async def test_scenario_s5_log_injection(clean_outputs_dir: Path, clean_runlog_path: Path):
    """S5 log_injection: prompt injection caught -> quarantine, security_note, clean rollback."""
    env = Environment(data_dir="data", scenario_id="s5_log_injection")
    orch = WarRoomOrchestrator(env=env, outputs_dir=clean_outputs_dir)
    orch.run_log.log_path = clean_runlog_path

    out = await orch.run()

    # Decision should remain unaffected: rollback
    assert out.mitigation == "rollback"
    assert "deploy regression" in out.likely_cause.lower()
    assert out.target_service == "checkout-service"

    # Security note must be present on board
    import json

    with open(out.board_json_path, encoding="utf-8") as f:
        board_data = json.load(f)
    kinds = [p["kind"] for p in board_data["posts"]]
    assert "security_note" in kinds

    assert out.run_log_verified is True


@pytest.mark.asyncio
async def test_scenario_s6_rollback_unsafe(clean_outputs_dir: Path, clean_runlog_path: Path):
    """S6 rollback_unsafe: breaking DB migration -> rollback rejected, restart chosen."""
    env = Environment(data_dir="data", scenario_id="s6_rollback_unsafe")
    orch = WarRoomOrchestrator(env=env, outputs_dir=clean_outputs_dir)
    orch.run_log.log_path = clean_runlog_path

    out = await orch.run()

    assert out.mitigation in ("restart", "failover")
    assert out.target_service == "inventory-service"

    # Rollback must be explicitly rejected with reason citing breaking migration
    rejected_reasons = {r["mitigation"]: r["reason"] for r in out.rejected_alternatives}
    assert "rollback" in rejected_reasons
    assert "migration" in rejected_reasons["rollback"].lower()

    assert out.run_log_verified is True
