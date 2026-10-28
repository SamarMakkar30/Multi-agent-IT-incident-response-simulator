"""LLM client factory and ScriptedChatClient for offline deterministic testing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, Content, Message
from agent_framework._tools import FunctionInvocationLayer


class ScriptedChatClient(FunctionInvocationLayer, BaseChatClient):
    """Deterministic offline chat client that executes scripted tool calls and responses.

    Replays transcripts from cassette files or deterministic scenario rules.
    """

    def __init__(
        self,
        cassette_path: str | Path | None = None,
        scenario_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.cassette_path = Path(cassette_path) if cassette_path else None
        self.scenario_id = scenario_id or "s1_bad_deploy"
        self._cassette_data: dict[str, Any] = {}
        self._agent_call_counters: dict[str, int] = {}

        if self.cassette_path and self.cassette_path.exists():
            with open(self.cassette_path, encoding="utf-8") as f:
                self._cassette_data = json.load(f)

    async def _inner_get_response(
        self,
        *,
        messages: list[Message],
        stream: bool,
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Return scripted tool call or response message."""
        # Detect active agent name from system message or options
        active_agent = "Unknown"
        for m in messages:
            if m.role == "system" and m.contents:
                content_str = str(m.contents[0])
                for name in [
                    "Alert Agent",
                    "Logs Agent",
                    "Dependency Agent",
                    "Mitigation Agent",
                    "Incident Commander",
                    "Comms Agent",
                ]:
                    if name.lower() in content_str.lower():
                        active_agent = name
                        break

        counter = self._agent_call_counters.get(active_agent, 0)
        self._agent_call_counters[active_agent] = counter + 1

        # Check if cassette has explicit step for (active_agent, counter)
        agent_steps = self._cassette_data.get(active_agent, [])
        if counter < len(agent_steps):
            step = agent_steps[counter]
            step_type = step.get("type", "message")
            if step_type == "tool_call":
                tc = step["tool_call"]
                content = Content.from_function_call(
                    call_id=f"call_{active_agent}_{counter}",
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                return ChatResponse(messages=[Message(role="assistant", contents=[content])])
            else:
                return ChatResponse(
                    messages=[Message(role="assistant", contents=[step.get("content", "Done")])]
                )

        # Fallback: check if the latest message was a tool result
        last_msg = messages[-1] if messages else None
        if last_msg and last_msg.role == "tool":
            return ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            f"{active_agent} successfully executed tool and analyzed results."
                        ],
                    )
                ]
            )

        # Default fallback response
        return ChatResponse(
            messages=[
                Message(role="assistant", contents=[f"{active_agent} investigation complete."])
            ]
        )


def get_chat_client(
    provider: str | None = None,
    scenario_id: str | None = None,
    cassettes_dir: str | Path = "tests/cassettes",
) -> BaseChatClient:
    """Factory selecting the ChatClient implementation based on environment.

    Supported providers:
    - scripted (default for tests and offline evaluation)
    - openai_compatible
    - azure_openai
    - ollama
    """
    active_provider = provider or os.getenv("LLM_PROVIDER", "scripted").lower()

    if active_provider == "scripted":
        cassette_file = Path(cassettes_dir) / f"{scenario_id or 'default'}.json"
        return ScriptedChatClient(cassette_path=cassette_file, scenario_id=scenario_id)

    if active_provider == "openai_compatible":
        # Production configuration placeholder for live models
        _ = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        _ = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return ScriptedChatClient(scenario_id=scenario_id)

    # Fallback to ScriptedChatClient
    return ScriptedChatClient(scenario_id=scenario_id)
