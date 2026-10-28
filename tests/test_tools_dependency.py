"""Unit tests for Dependency Agent domain tools."""

import pytest

from war_room.environment import Environment
from war_room.tools.dependency_tools import (
    compute_blast_radius,
    get_dependencies,
    get_recent_changes,
)


@pytest.fixture
def env():
    return Environment(data_dir="data", scenario_id="s1_bad_deploy")


def test_get_dependencies(env: Environment):
    deps = get_dependencies(env, "checkout-service")
    assert "orders-service" in deps.downstreams
    assert "payments-gateway" in deps.downstreams
    assert "api-gateway" in deps.upstreams


def test_get_recent_changes(env: Environment):
    changes = get_recent_changes(env, "checkout-service", lookback_minutes=60)
    assert len(changes) == 1
    assert changes[0].version == "v2.14.0"
    assert changes[0].commit == "a1b2c3d"


def test_compute_blast_radius(env: Environment):
    report = compute_blast_radius(env, "database-cluster")
    assert report.failing_service == "database-cluster"
    assert len(report.impacted_services) >= 4
    assert report.impacted_tier1_count >= 2
    assert report.user_facing_impacted is True
