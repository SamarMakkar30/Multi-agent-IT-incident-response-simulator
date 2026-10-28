"""Append-only, SHA-256 tamper-evident run log for auditability."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def _canonical_json(data: dict[str, Any]) -> str:
    """Serialize dictionary to deterministic, canonical JSON."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def compute_entry_hash(entry_without_hash: dict[str, Any], prev_hash: str) -> str:
    """Compute SHA-256 hash chaining this entry to the predecessor hash."""
    canonical = _canonical_json(entry_without_hash)
    payload = f"{canonical}|{prev_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RunLog:
    """Append-only tamper-evident audit logger."""

    def __init__(
        self,
        log_path: str | Path = "logs/run_log.jsonl",
        run_id: str = "default",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.run_id = run_id
        self.log_path = Path(log_path)

    @property
    def log_path(self) -> Path:
        """Path to the append-only JSONL log file."""
        return self._log_path

    @log_path.setter
    def log_path(self, path: str | Path) -> None:
        self._log_path = Path(path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._last_hash = self._read_last_seq_and_hash()

    def _read_last_seq_and_hash(self) -> tuple[int, str]:
        """Read the last sequence number and hash from existing log file."""
        if not self._log_path.exists() or self._log_path.stat().st_size == 0:
            return 0, GENESIS_HASH

        last_seq = 0
        last_hash = GENESIS_HASH
        with open(self._log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    last_seq = entry.get("seq", last_seq)
                    last_hash = entry.get("hash", last_hash)
                except json.JSONDecodeError:
                    continue
        return last_seq, last_hash

    def append(
        self,
        agent: str,
        event_type: str,
        payload: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Append an audit record to the log. File is opened strictly in append mode."""
        self._seq += 1
        seq = self._seq
        ts = self._clock().isoformat()
        active_run_id = run_id or self.run_id
        prev_hash = self._last_hash

        entry_data: dict[str, Any] = {
            "run_id": active_run_id,
            "seq": seq,
            "ts": ts,
            "agent": agent,
            "event_type": event_type,
            "payload": payload,
            "prev_hash": prev_hash,
        }

        entry_hash = compute_entry_hash(entry_data, prev_hash)
        entry_data["hash"] = entry_hash

        # Strictly append mode ("a")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry_data, default=str) + "\n")

        self._last_hash = entry_hash
        return entry_data


def verify_chain(log_path: str | Path) -> tuple[bool, str | None]:
    """Verify unbroken SHA-256 hash linkage across all entries in the log file.

    Returns:
        (True, None) if valid.
        (False, error_message) if tampered, missing, or malformed.
    """
    path = Path(log_path)
    if not path.exists() or path.stat().st_size == 0:
        return True, None  # Empty log is vacuously valid

    expected_seq = 1
    expected_prev_hash = GENESIS_HASH

    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                return False, f"Line {line_num}: Invalid JSON ({e})"

            # Verify sequence continuity
            entry_seq = entry.get("seq")
            if entry_seq != expected_seq:
                return (
                    False,
                    f"Line {line_num}: Sequence mismatch. "
                    f"Expected {expected_seq}, found {entry_seq}",
                )

            # Verify previous hash linkage
            entry_prev_hash = entry.get("prev_hash")
            if entry_prev_hash != expected_prev_hash:
                return (
                    False,
                    f"Line {line_num} (seq {entry_seq}): prev_hash mismatch. "
                    f"Expected {expected_prev_hash}, found {entry_prev_hash}",
                )

            # Recompute entry hash
            entry_hash = entry.get("hash")
            raw_entry = {k: v for k, v in entry.items() if k != "hash"}
            recomputed = compute_entry_hash(raw_entry, entry_prev_hash)

            if recomputed != entry_hash:
                return (
                    False,
                    f"Line {line_num} (seq {entry_seq}): Hash mismatch. "
                    f"Content altered! Stored: {entry_hash}, Recomputed: {recomputed}",
                )

            expected_prev_hash = entry_hash
            expected_seq += 1

    return True, None
