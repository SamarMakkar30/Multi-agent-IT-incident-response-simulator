.PHONY: install lint test demo clean

PYTHON ?= .venv/Scripts/python.exe
RUFF ?= .venv/Scripts/ruff.exe
PYTEST ?= .venv/Scripts/pytest.exe

install:
	uv pip install --python $(PYTHON) agent-framework-core pydantic pytest pytest-asyncio ruff

lint:
	$(RUFF) check .

format:
	$(RUFF) format --check .

test:
	$(PYTEST) -q

demo:
	PYTHONPATH=src $(PYTHON) -m war_room.orchestrator --scenario s1_bad_deploy --demo

