"""Unit tests for Mitigation Agent domain tools."""

import pytest

from war_room.environment import Environment
from war_room.retrieval import BM25Index
from war_room.tools.mitigation_tools import (
    check_failover_readiness,
    find_similar_past_incidents,
    get_rollback_candidates,
    search_runbooks,
)


@pytest.fixture
def env():
    return Environment(data_dir="data", scenario_id="s1_bad_deploy")


@pytest.fixture
def runbook_index(env: Environment):
    index = BM25Index[dict]()
    for rb in env.get_runbooks():
        index.add_document(rb["doc_id"], rb["content"], rb)
    return index


@pytest.fixture
def incidents_index(env: Environment):
    index = BM25Index[dict]()
    for inc in env.get_past_incidents():
        text = f"{inc['title']} {inc['symptoms']} {inc['root_cause']}"
        index.add_document(inc["incident_id"], text, inc)
    return index


def test_search_runbooks(runbook_index):
    matches = search_runbooks(runbook_index, "deployment rollback procedure", top_k=2)
    assert len(matches) > 0
    assert "RB-001-deploy-rollback" in [m.doc_id for m in matches]


def test_find_similar_past_incidents(incidents_index):
    matches = find_similar_past_incidents(
        incidents_index, "checkout 5xx error after deploy", top_k=2
    )
    assert len(matches) > 0
    assert matches[0].resolution == "rollback"


def test_get_rollback_candidates_safe(env: Environment):
    candidates = get_rollback_candidates(env, "checkout-service")
    assert len(candidates) == 1
    assert candidates[0].target_version == "v2.13.4"
    assert candidates[0].is_safe is True
    assert candidates[0].breaking_db_migration is False


def test_get_rollback_candidates_unsafe():
    # s6 has inventory-service with breaking_db_migration=True
    s6_env = Environment(data_dir="data", scenario_id="s6_rollback_unsafe")
    candidates = get_rollback_candidates(s6_env, "inventory-service")
    assert len(candidates) == 1
    assert candidates[0].is_safe is False
    assert candidates[0].breaking_db_migration is True
    assert "UNSAFE" in candidates[0].reason


def test_check_failover_readiness():
    s3_env = Environment(data_dir="data", scenario_id="s3_upstream_outage")
    report = check_failover_readiness(s3_env, "payments-gateway")
    assert report.has_secondary is True
    assert report.secondary_target == "external-payments-secondary"
    assert report.is_ready is True
