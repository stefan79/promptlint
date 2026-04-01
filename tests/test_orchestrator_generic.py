from promptlint.gateways.normalizer import NormalizedMessage, NormalizedRequest
from promptlint.orchestrators.generic import GenericAdapter


def _make_request(
    vendor: str = "anthropic",
    system_prompt: str | None = "Be helpful",
    tools: list[dict[str, object]] | None = None,
    messages: list[NormalizedMessage] | None = None,
) -> NormalizedRequest:
    return NormalizedRequest(
        vendor=vendor,
        system_prompt=system_prompt,
        tools=tools or [],
        messages=messages or [],
        raw_body=b"{}",
    )


def test_always_matches() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request())
    assert ctx is not None
    assert ctx.orchestrator_name == "generic"


def test_system_source_anthropic() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request(vendor="anthropic"))
    assert ctx.system_prompt_source == "body.system"


def test_system_source_openai() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request(vendor="openai"))
    assert ctx.system_prompt_source == "messages[0]"


def test_system_source_gemini() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request(vendor="gemini"))
    assert ctx.system_prompt_source == "body.system_instruction"


def test_system_source_unknown_vendor() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request(vendor="some-new-vendor"))
    assert ctx.system_prompt_source == "unknown"


def test_extract_anthropic_tools() -> None:
    adapter = GenericAdapter()
    tools: list[dict[str, object]] = [
        {
            "name": "Read",
            "input_schema": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}, "limit": {"type": "number"}},
            },
        }
    ]
    ctx = adapter.detect(_make_request(tools=tools))
    assert len(ctx.tools) == 1
    assert ctx.tools[0].name == "Read"
    assert ctx.tools[0].param_count == 2


def test_extract_openai_tools() -> None:
    adapter = GenericAdapter()
    tools: list[dict[str, object]] = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                },
            },
        }
    ]
    ctx = adapter.detect(_make_request(vendor="openai", tools=tools))
    assert len(ctx.tools) == 1
    assert ctx.tools[0].name == "get_weather"
    assert ctx.tools[0].param_count == 1


def test_extract_gemini_tools() -> None:
    adapter = GenericAdapter()
    tools: list[dict[str, object]] = [
        {
            "name": "search",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            },
        }
    ]
    ctx = adapter.detect(_make_request(vendor="gemini", tools=tools))
    assert len(ctx.tools) == 1
    assert ctx.tools[0].name == "search"
    assert ctx.tools[0].param_count == 2


def test_empty_tools() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request(tools=[]))
    assert ctx.tools == []


def test_tool_with_no_name_skipped() -> None:
    adapter = GenericAdapter()
    tools: list[dict[str, object]] = [{"input_schema": {"type": "object", "properties": {"x": {}}}}]
    ctx = adapter.detect(_make_request(tools=tools))
    assert ctx.tools == []


def test_tool_with_no_schema() -> None:
    adapter = GenericAdapter()
    tools: list[dict[str, object]] = [{"name": "simple_tool"}]
    ctx = adapter.detect(_make_request(tools=tools))
    assert len(ctx.tools) == 1
    assert ctx.tools[0].name == "simple_tool"
    assert ctx.tools[0].param_count == 0


def test_empty_messages() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request(messages=[]))
    assert ctx.orchestrator_name == "generic"
    assert ctx.skills == []
    assert ctx.agents == []


def test_no_skills_or_agents() -> None:
    adapter = GenericAdapter()
    ctx = adapter.detect(_make_request())
    assert ctx.skills == []
    assert ctx.agents == []
