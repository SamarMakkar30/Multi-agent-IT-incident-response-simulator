"""Unit tests for the pure-Python Okapi BM25 retrieval engine."""

import pytest

from war_room.environment import Environment
from war_room.retrieval import BM25Index


@pytest.fixture
def env():
    return Environment(data_dir="data", scenario_id="s1_bad_deploy")


def test_bm25_empty_and_basic_search():
    index = BM25Index[dict]()
    index.add_document("doc1", "deployment rollback procedure after 500 error", {"id": 1})
    index.add_document("doc2", "memory leak and out of memory crash restart", {"id": 2})
    index.add_document("doc3", "database connection pool timeout failover", {"id": 3})

    results = index.search("rollback deploy 500 error", top_k=2)
    assert len(results) >= 1
    assert results[0].doc_id == "doc1"
    assert results[0].score > 0.0

    mem_results = index.search("out of memory crash heap", top_k=1)
    assert len(mem_results) == 1
    assert mem_results[0].doc_id == "doc2"


def test_bm25_runbook_corpus(env: Environment):
    index = BM25Index[dict]()
    runbooks = env.get_runbooks()
    for rb in runbooks:
        index.add_document(rb["doc_id"], rb["content"], rb)

    # Search for rollback scenario
    results = index.search("deploy 5xx error regression rollback", top_k=3)
    assert len(results) > 0
    top_doc_ids = [r.doc_id for r in results]
    assert "RB-001-deploy-rollback" in top_doc_ids

    # Search for gateway failover scenario
    gw_results = index.search("payment gateway timeout provider failover", top_k=3)
    top_gw_ids = [r.doc_id for r in gw_results]
    assert "RB-003-gateway-failover" in top_gw_ids


def test_bm25_past_incidents_memory(env: Environment):
    index = BM25Index[dict]()
    incidents = env.get_past_incidents()
    for inc in incidents:
        text = f"{inc['title']} {inc['symptoms']} {inc['root_cause']}"
        index.add_document(inc["incident_id"], text, inc)

    results = index.search("checkout 5xx spike null pointer discount", top_k=3)
    assert len(results) > 0
    assert results[0].doc_id == "INC-HIST-001"
    assert results[0].document["resolution"] == "rollback"
