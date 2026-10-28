# Changelog

All notable changes to the IT Incident Response War-Room project will be documented in this file.

## [Unreleased]

## [0.6.0] - 2026-10-28
### Added
- Phase 5: Multi-Agent Modules & LLM Client.
- `src/war_room/llm.py`: Provider factory with `ScriptedChatClient` for deterministic offline execution.
- `src/war_room/agents/`: 6 distinct agent modules each with single role and builder:
  - `alert_agent.py`, `logs_agent.py`, `dependency_agent.py`, `mitigation_agent.py`, `commander_agent.py`, `comms_agent.py`.
- `tests/test_architecture.py`: Structural AST conformance tests asserting module boundaries, tool counts, zero cross-agent imports, least-privilege Commander, and immutable board (46 total tests passing).

## [0.5.0] - 2026-10-28
### Added
- Phase 4: Typed Domain Tools.
- `src/war_room/tools/`: 6 tool modules with Pydantic inputs and outputs.
  - `alert_tools.py`: `parse_alert`, `score_severity`, `get_service_metadata`.
  - `logs_tools.py`: `search_logs`, `summarize_error_signatures`, `find_error_onset`.
  - `dependency_tools.py`: `get_dependencies`, `check_service_health`, `get_recent_changes`, `compute_blast_radius`.
  - `mitigation_tools.py`: `search_runbooks`, `find_similar_past_incidents`, `get_rollback_candidates`, `check_failover_readiness`.
  - `commander_tools.py`: `read_board`, `validate_evidence`, `record_decision`, `request_evidence`, `build_timeline`, `escalate_to_human`.
  - `comms_tools.py`: `get_status_template`, `render_status_update`, `check_comms_policy`.
- `tests/test_tools_*.py`: 6 comprehensive tool test suites (41 total tests passing).

## [0.4.0] - 2026-10-28
### Added
- Phase 3: Explainable Retrieval & Safety Guards.
- `src/war_room/retrieval.py`: Pure-Python Okapi BM25 retrieval engine with tokenization and explainable document scoring.
- `src/war_room/guards.py`: Adversarial prompt-injection quarantine scanner, multi-author evidence guard, and confidence gate.
- `tests/test_retrieval.py` and `tests/test_guards.py`: Unit tests validating BM25 rankings and guardrails (22 total tests passing).

## [0.3.0] - 2026-10-28
### Added
- Phase 2: Synthetic Data & Reproducible Environment.
- `data/topology.json`: 12 services across Tiers 1-3 with dependencies, SLOs, and ownership.
- `data/deploys.json`: Historical releases with commit SHAs, timestamps, and DB migration risk flags.
- `data/runbooks/`: 10 Markdown runbooks covering rollbacks, restarts, failovers, pool exhaustion, and migrations.
- `data/past_incidents.json`: 15 past incidents with root causes and resolutions.
- `data/scenarios/`, `data/logs/`, and `data/metrics/`: Complete synthetic datasets for scenarios S1 through S6.
- `src/war_room/environment.py`: `Environment` simulation engine with time-bounded reproducible queries.
- `tests/test_environment.py`: Unit tests validating topology, deploys, logs, and runbooks.

## [0.2.0] - 2026-10-28
### Added
- Phase 1: Core Blackboard and Append-Only Run Log.
- `src/war_room/board.py`: Pydantic `Post`, `PostKind`, `IncidentBoard`, `BoardHandle`, permission matrix, and concurrency lock.
- `src/war_room/runlog.py`: Append-only JSONL logger with SHA-256 hash chaining and `verify_chain()` tamper detection.
- `tests/test_board.py` and `tests/test_runlog.py`: 8 passing unit tests.

## [0.1.0] - 2026-10-28
### Added
- Phase 0: Project setup and verification.
- `.venv` virtual environment with Python 3.11.4 and `agent-framework-core` 1.23.0.
- `docs/framework_notes.md` documenting verified classes and extension points.
- `docs/DECISIONS.md` documenting architectural decisions ADR-001 through ADR-005.
- `.env.example` and `Makefile`.
