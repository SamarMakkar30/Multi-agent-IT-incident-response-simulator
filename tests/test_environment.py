"""Unit tests for the Simulated Environment engine."""

from datetime import UTC, datetime

import pytest

from war_room.environment import Environment


@pytest.fixture
def env():
    return Environment(data_dir="data", scenario_id="s1_bad_deploy")


def test_environment_loads_topology(env: Environment):
    meta = env.get_service_metadata("checkout-service")
    assert meta is not None
    assert meta["tier"] == 1
    assert meta["owner"] == "team-checkout"
    assert meta["user_facing"] is True

    deps = env.get_dependencies("checkout-service")
    assert "orders-service" in deps["downstreams"]
    assert "api-gateway" in deps["upstreams"]


def test_environment_deploys_filtered_by_now(env: Environment):
    # s1 simulation now is 2026-10-28T10:30:00Z
    # Deploy was at 10:15:00Z
    deploys = env.get_deploys("checkout-service", lookback_minutes=30)
    assert len(deploys) == 1
    assert deploys[0]["version"] == "v2.14.0"

    # Future deploy simulation
    early_env = Environment(
        data_dir="data",
        scenario_id="s1_bad_deploy",
        now=datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC),
    )
    early_deploys = early_env.get_deploys("checkout-service", lookback_minutes=30)
    assert len(early_deploys) == 0


def test_environment_logs_retrieval(env: Environment):
    logs = env.get_logs("checkout-service", query="NullPointerException")
    assert len(logs) >= 4
    assert "NullPointerException" in logs[0]["signature"]


def test_environment_runbooks_and_past_incidents(env: Environment):
    runbooks = env.get_runbooks()
    assert len(runbooks) >= 10
    doc_ids = [rb["doc_id"] for rb in runbooks]
    assert "RB-001-deploy-rollback" in doc_ids
    assert "RB-002-memory-leak-restart" in doc_ids

    incidents = env.get_past_incidents()
    assert len(incidents) >= 15
