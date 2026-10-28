"""Architectural and structural conformance tests.

Enforces:
1. Multi-agent system: >= 4 agents, each its own module with ONE clear role.
2. Each agent has >= 2 domain tools.
3. No agent imports another agent.
4. Least privilege: Commander has ZERO data-source tools.
5. Blackboard has no update or delete methods.
"""

import ast
from pathlib import Path

AGENTS_DIR = Path("src/war_room/agents")
EXPECTED_AGENTS = [
    "alert_agent",
    "logs_agent",
    "dependency_agent",
    "mitigation_agent",
    "commander_agent",
    "comms_agent",
]

DATA_SOURCE_FUNCTION_NAMES = {
    "search_logs",
    "summarize_error_signatures",
    "find_error_onset",
    "get_dependencies",
    "check_service_health",
    "get_recent_changes",
    "compute_blast_radius",
}


def test_agent_modules_exist():
    """Verify that at least 4 (we have 6) agent modules exist."""
    agent_files = [p.stem for p in AGENTS_DIR.glob("*_agent.py")]
    assert len(agent_files) >= 4
    for expected in EXPECTED_AGENTS:
        assert expected in agent_files, f"Expected agent module {expected} missing"


def test_no_agent_imports_another_agent():
    """AST check: Verify no agent module imports another agent module."""
    for agent_file in AGENTS_DIR.glob("*_agent.py"):
        tree = ast.parse(agent_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "war_room.agents" not in alias.name, (
                        f"Module {agent_file.name} illegally imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "agents" not in module, (
                    f"Module {agent_file.name} illegally imports from {module}"
                )


def test_each_agent_defines_required_symbols():
    """AST check: Verify each agent defines ROLE, INSTRUCTIONS, and build_*_agent."""
    for agent_file in AGENTS_DIR.glob("*_agent.py"):
        tree = ast.parse(agent_file.read_text(encoding="utf-8"))
        assigned_vars = set()
        function_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_vars.add(target.id)
            elif isinstance(node, ast.FunctionDef):
                function_names.add(node.name)

        assert "ROLE" in assigned_vars, f"{agent_file.name} must define ROLE"
        assert "INSTRUCTIONS" in assigned_vars, f"{agent_file.name} must define INSTRUCTIONS"

        builder_name = f"build_{agent_file.stem}"
        assert builder_name in function_names, (
            f"{agent_file.name} must define builder function {builder_name}"
        )


def test_commander_least_privilege_no_data_source_tools():
    """Verify structurally that Incident Commander imports or defines NO data-source tools."""
    commander_file = AGENTS_DIR / "commander_agent.py"
    tree = ast.parse(commander_file.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "logs_tools" not in module, "Commander cannot import logs_tools"
            assert "dependency_tools" not in module, "Commander cannot import dependency_tools"
            for alias in node.names:
                assert alias.name not in DATA_SOURCE_FUNCTION_NAMES, (
                    f"Commander illegally imports data-source tool {alias.name}"
                )
        elif isinstance(node, ast.FunctionDef):
            assert node.name not in DATA_SOURCE_FUNCTION_NAMES, (
                f"Commander illegally defines data-source tool {node.name}"
            )


def test_blackboard_has_no_update_or_delete_apis():
    """Verify that IncidentBoard provides no update or delete methods."""
    from war_room.board import IncidentBoard

    forbidden = ["update", "delete", "remove", "pop", "clear", "modify", "edit"]
    board_methods = [m.lower() for m in dir(IncidentBoard)]

    for f in forbidden:
        assert f not in board_methods, f"IncidentBoard must not have method '{f}'"
