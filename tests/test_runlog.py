"""Unit tests for append-only, SHA-256 tamper-evident run log."""

import json
from pathlib import Path

import pytest

from war_room.runlog import RunLog, verify_chain


@pytest.fixture
def run_log_file(tmp_path: Path):
    return tmp_path / "run_log.jsonl"


def test_runlog_append_and_verify_clean(run_log_file: Path):
    log = RunLog(log_path=run_log_file, run_id="run-001")

    # Append 5 events
    for i in range(1, 6):
        log.append(
            agent=f"Agent-{i}",
            event_type="tool_call",
            payload={"step": i, "status": "ok"},
        )

    # Verify unbroken chain
    is_valid, err = verify_chain(run_log_file)
    assert is_valid is True
    assert err is None


def test_runlog_detects_content_tampering(run_log_file: Path):
    log = RunLog(log_path=run_log_file, run_id="run-001")
    for i in range(1, 4):
        log.append(agent=f"Agent-{i}", event_type="tool_call", payload={"step": i})

    # Tamper with line 2 by altering its payload
    lines = run_log_file.read_text(encoding="utf-8").strip().split("\n")
    entry_2 = json.loads(lines[1])
    entry_2["payload"]["step"] = 999  # Malicious edit
    lines[1] = json.dumps(entry_2)
    run_log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    is_valid, err = verify_chain(run_log_file)
    assert is_valid is False
    assert err is not None
    assert "Hash mismatch" in err
    assert "seq 2" in err


def test_runlog_detects_line_deletion(run_log_file: Path):
    log = RunLog(log_path=run_log_file, run_id="run-001")
    for i in range(1, 5):
        log.append(agent=f"Agent-{i}", event_type="board_post", payload={"item": i})

    # Delete line 2
    lines = run_log_file.read_text(encoding="utf-8").strip().split("\n")
    del lines[1]
    run_log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    is_valid, err = verify_chain(run_log_file)
    assert is_valid is False
    assert err is not None
    assert "Sequence mismatch" in err or "prev_hash mismatch" in err


def test_runlog_detects_reordering(run_log_file: Path):
    log = RunLog(log_path=run_log_file, run_id="run-001")
    for i in range(1, 4):
        log.append(agent=f"Agent-{i}", event_type="decision", payload={"index": i})

    # Swap line 1 and line 2
    lines = run_log_file.read_text(encoding="utf-8").strip().split("\n")
    lines[0], lines[1] = lines[1], lines[0]
    run_log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    is_valid, err = verify_chain(run_log_file)
    assert is_valid is False
