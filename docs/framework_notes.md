# Framework Notes: Microsoft Agent Framework (Python)

## 1. Package Verification
- **Package Name**: `agent-framework-core` (part of the official Microsoft Agent Framework release series)
- **Version Verified**: `1.23.0`
- **Python Version**: Python 3.11.4
- **Inspection Date**: 2026-10-28
- **Installation Location**: `.venv/Lib/site-packages/agent_framework/`

## 2. Verified Class Hierarchy & Signatures

### Agent Abstraction
- **Class**: `agent_framework.Agent`
- **Inheritance**: `Agent(AgentMiddlewareLayer, AgentTelemetryLayer, RawAgent[OptionsCoT], Generic[OptionsCoT])`
- **Constructor Signature**:
  ```python
  Agent(
      client: SupportsChatGetResponse[OptionsCoT],
      instructions: str | None = None,
      *,
      id: str | None = None,
      name: str | None = None,
      description: str | None = None,
      tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
      default_options: OptionsCoT | None = None,
      context_providers: Sequence[ContextProvider] | None = None,
      middleware: Sequence[MiddlewareTypes] | None = None,
      require_per_service_call_history_persistence: bool = False,
      compaction_strategy: CompactionStrategy | None = None,
      tokenizer: TokenizerProtocol | None = None,
      additional_properties: MutableMapping[str, Any] | None = None,
  ) -> None
  ```
- **Execution Method**:
  ```python
  async def run(
      messages: AgentRunInputs | None = None,
      *,
      stream: bool = False,
      ...
  ) -> AgentResponse[Any]
  ```

### Tool Definition & Invocations
- **Decorator**: `@tool` (or `agent_framework.tool`) wraps a standard Python function into a `FunctionTool`.
- **Metadata**: Uses function type hints for parameter schemas and the docstring as the tool description.
- **Client Tool Loop Execution**: To enable seamless tool invocation inside `Agent.run()`, chat clients must inherit from both `agent_framework._tools.FunctionInvocationLayer` and `agent_framework.BaseChatClient`.

### Client Extension Point (`BaseChatClient`)
- **Base Classes**: `agent_framework._tools.FunctionInvocationLayer`, `agent_framework.BaseChatClient`
- **Core Method to Override**:
  ```python
  async def _inner_get_response(
      self,
      *,
      messages: Sequence[Message],
      stream: bool,
      options: Mapping[str, Any],
      **kwargs: Any,
  ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]
  ```
- **Message Construction**:
  - `Message(role="assistant" | "user" | "system" | "tool", contents=[...])`
  - Function calling output:
    ```python
    Content.from_function_call(call_id="call_1", name="tool_name", arguments={"param": val})
    ```
  - Standard assistant text response:
    ```python
    Content.from_text("Response text") # or contents=["Response text"]
    ```

## 3. Findings & Architectural Strategy
1. `ScriptedChatClient` will inherit from `(FunctionInvocationLayer, BaseChatClient)`. This allows deterministic cassette replay while fully supporting the native framework's multi-turn tool invocation loop.
2. Production clients (`OpenAIChatClient`, `AzureChatClient`, `OllamaChatClient`) wrap standard API endpoints through the same interface.
3. Conformance tests verify that all agents in `src/war_room/agents/` are constructed via `build_<name>_agent(client, board_handle, ...)` returning `agent_framework.Agent`.
