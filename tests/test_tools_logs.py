"""Unit tests for Logs Agent domain tools."""

import pytest

from war_room.environment import Environment
from war_room.tools.logs_tools import (
    find_error_onset,
    search_logs,
    summarize_error_signatures,
)


@pytest.fixture
def env():
    return Environment(data_dir="data", scenario_id="s1_bad_deploy")


def test_search_logs(env: Environment):
    res = search_logs(env, "checkout-service", query="NullPointerException")
    assert res.match_count >= 4
    assert res.service == "checkout-service"
    assert "NullPointerException" in res.entries[0].message


def test_summarize_error_signatures(env: Environment):
    summaries = summarize_error_signatures(env, "checkout-service")
    assert len(summaries) >= 1
    top_sig = summaries[0]
    assert "NullPointerException" in top_sig.signature
    assert top_sig.count >= 4


def test_find_error_onset(env: Environment):
    onset = find_error_onset(env, "checkout-service", "NullPointerException")
    assert onset.onset_timestamp is not None
    assert "10:17:02" in onset.onset_timestamp
