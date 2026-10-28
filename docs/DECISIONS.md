# Architectural Decisions Log (DECISIONS.md)

## ADR-001: Blackboard Architecture vs Direct Agent-to-Agent Messaging
- **Context**: In complex production incidents, investigations progress non-linearly. Specialists (logs, dependency topology, runbooks) discover facts asynchronously.
- **Decision**: All agent communication occurs exclusively through a single, shared, append-only `IncidentBoard`. Agents never invoke or message each other directly. Workflow steps pass only the string `incident_id` as a reference.
- **Consequences**:
  - Eliminates tight coupling between agents.
  - Guarantees full auditability and provides a complete historical substrate for the postmortem timeline.
  - Incident Commander decisions are verifiably grounded only in posted evidence.

## ADR-002: Pure-Python BM25 Retrieval vs Vector Database
- **Context**: The war-room requires short-term memory (the Board), runbook search, and historical incident retrieval. External vector databases introduce opaque embeddings, API credentials, and non-determinism during offline grading.
- **Decision**: Implement a clean, pure-Python Okapi BM25 index ($k_1=1.5, b=0.75$) with transparent tokenization.
- **Consequences**:
  - Zero external database services, zero network calls, 100% offline deterministic execution.
  - Every retrieved search result returns an explicit `doc_id` and float `score` directly explainable during a university viva.

## ADR-003: Scripted Cassette Replay for Deterministic Offline Testing
- **Context**: Automated tests and the demo notebook must pass offline without API keys or live LLM network access.
- **Decision**: Implement `ScriptedChatClient` implementing `agent_framework.BaseChatClient` and `FunctionInvocationLayer`. The client matches input messages against recorded JSON cassettes in `tests/cassettes/`.
- **Consequences**:
  - `pytest` runs in seconds with 100% determinism.
  - `demo.ipynb` can run "Restart and Run All" anywhere with zero network setup.
  - Production deployments switch seamlessly to `openai_compatible` or `azure_openai` via `LLM_PROVIDER` in `.env`.

## ADR-004: Structural Least-Privilege for Incident Commander
- **Context**: The rule dictates: "The Incident Commander may decide ONLY from evidence posted on the board and must record every step." Prompt-only instructions risk model hallucination.
- **Decision**: Commander agent is structurally denied all data-source tools (no access to `search_logs`, `get_dependencies`, etc.). The Commander toolset consists solely of `read_board`, `validate_evidence`, `record_decision`, `request_evidence`, `build_timeline`, and `escalate_to_human`.
- **Consequences**:
  - Structurally impossible for Commander to query raw system state.
  - Enforced by AST architectural conformance test (`test_architecture.py`).

## ADR-005: Dual-Timestamp Postmortem Timeline Construction
- **Context**: Output Contract requires chronological timeline with `incident_time` (when it happened in the system) and `war_room_time` (when an agent posted it).
- **Decision**: `Post` models support both `posted_at` (war room clock) and optional `incident_time` (extracted from log timestamps or deployment records). The postmortem timeline builder extracts and formats both columns deterministically without freehand LLM generation.

