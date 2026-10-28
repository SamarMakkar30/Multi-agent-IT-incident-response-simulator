"""Simulated Environment providing reproducible access to synthetic telemetry.

Parameterized by injected simulation 'now' timestamp for offline determinism.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class Environment:
    """Provides time-bounded, deterministic access to all scenario telemetry."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        scenario_id: str = "s1_bad_deploy",
        now: datetime | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.scenario_id = scenario_id

        # Load scenario spec to extract default simulation now if not provided
        self._scenario_spec = self._load_scenario_spec()
        if now is not None:
            self._now = now
        else:
            sim_now_str = self._scenario_spec.get("simulation_now")
            if sim_now_str:
                self._now = datetime.fromisoformat(sim_now_str.replace("Z", "+00:00"))
            else:
                self._now = datetime.now(UTC)

        self._topology = self._load_json(self.data_dir / "topology.json")
        self._deploys = self._load_json(self.data_dir / "deploys.json").get("deploys", [])
        self._past_incidents = self._load_json(self.data_dir / "past_incidents.json").get(
            "incidents", []
        )

    @property
    def now(self) -> datetime:
        """The simulated 'now' timestamp."""
        return self._now

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_scenario_spec(self) -> dict[str, Any]:
        scenario_path = self.data_dir / "scenarios" / f"{self.scenario_id}.json"
        return self._load_json(scenario_path)

    def get_scenario_spec(self) -> dict[str, Any]:
        return dict(self._scenario_spec)

    def get_service_metadata(self, service_name: str) -> dict[str, Any] | None:
        services = self._topology.get("services", {})
        return services.get(service_name)

    def get_dependencies(self, service_name: str) -> dict[str, list[str]]:
        meta = self.get_service_metadata(service_name)
        if not meta:
            return {"upstreams": [], "downstreams": []}
        return meta.get("dependencies", {"upstreams": [], "downstreams": []})

    def get_all_services(self) -> list[str]:
        return list(self._topology.get("services", {}).keys())

    def get_deploys(
        self,
        service_name: str | None = None,
        lookback_minutes: int = 120,
    ) -> list[dict[str, Any]]:
        """Get deploys that occurred before `self.now` within `lookback_minutes`."""
        earliest = self._now - timedelta(minutes=lookback_minutes)
        results = []
        for d in self._deploys:
            if service_name and d.get("service") != service_name:
                continue
            deploy_ts = datetime.fromisoformat(d["deployed_at"].replace("Z", "+00:00"))
            if earliest <= deploy_ts <= self._now:
                results.append(d)
        # Sort newest first
        results.sort(
            key=lambda x: datetime.fromisoformat(x["deployed_at"].replace("Z", "+00:00")),
            reverse=True,
        )
        return results

    def get_latest_deploy(self, service_name: str) -> dict[str, Any] | None:
        """Get the most recent deploy for a service before `self.now`."""
        deploys = self.get_deploys(service_name=service_name, lookback_minutes=60 * 24 * 30)
        return deploys[0] if deploys else None

    def get_metrics(self, service_name: str) -> dict[str, Any] | None:
        metrics_file = self.data_dir / "metrics" / f"{self.scenario_id}.json"
        data = self._load_json(metrics_file)
        if data.get("service") == service_name:
            return data
        # Fallback default healthy metrics if service not in scenario anomaly
        meta = self.get_service_metadata(service_name)
        if meta:
            return {
                "service": service_name,
                "time_window_minutes": 30,
                "metrics": {
                    "http_error_rate_5xx": 0.0001,
                    "p99_latency_ms": 45,
                    "cpu_utilization": 0.20,
                    "memory_utilization": 0.35,
                    "request_volume_rpm": 5000,
                    "container_restarts": 0,
                },
                "health_status": "HEALTHY",
            }
        return None

    def get_logs(
        self,
        service_name: str | None = None,
        query: str | None = None,
        time_window_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Read scenario logs strictly prior to `self.now` within time window."""
        log_file = self.data_dir / "logs" / f"{self.scenario_id}.jsonl"
        if not log_file.exists():
            return []

        earliest = self._now - timedelta(minutes=time_window_minutes)
        results = []

        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if ts < earliest or ts > self._now:
                    continue

                if service_name and entry.get("service") != service_name:
                    continue

                if query:
                    q_lower = query.lower()
                    msg = entry.get("message", "").lower()
                    sig = entry.get("signature", "").lower()
                    if q_lower not in msg and q_lower not in sig:
                        continue

                results.append(entry)

        return results

    def get_runbooks(self) -> list[dict[str, str]]:
        """Load all markdown runbooks in data/runbooks/."""
        runbooks = []
        runbooks_dir = self.data_dir / "runbooks"
        if runbooks_dir.exists():
            for p in sorted(runbooks_dir.glob("*.md")):
                content = p.read_text(encoding="utf-8")
                runbooks.append({"doc_id": p.stem, "filename": p.name, "content": content})
        return runbooks

    def get_past_incidents(self) -> list[dict[str, Any]]:
        return list(self._past_incidents)
