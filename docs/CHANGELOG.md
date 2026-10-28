# Changelog

All notable changes to the IT Incident Response War-Room project will be documented in this file.

## [Unreleased]

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
