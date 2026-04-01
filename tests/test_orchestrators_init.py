from promptlint.gateways.normalizer import NormalizedMessage, NormalizedRequest, ToolCall
from promptlint.orchestrators import (
    DetectedContext,
    clear_adapters,
    detect,
    get_adapters,
    register_adapter,
    register_default_adapters,
)
from promptlint.orchestrators.claude_code import ClaudeCodeAdapter
from promptlint.orchestrators.generic import GenericAdapter


def _make_request(
    messages: list[NormalizedMessage] | None = None,
    system_prompt: str | None = None,
    tools: list[dict[str, object]] | None = None,
    vendor: str = "anthropic",
) -> NormalizedRequest:
    return NormalizedRequest(
        vendor=vendor,
        system_prompt=system_prompt,
        tools=tools or [],
        messages=messages or [],
        raw_body=b"{}",
    )


def setup_function() -> None:
    clear_adapters()


def teardown_function() -> None:
    clear_adapters()


def test_detect_returns_unknown_no_adapters() -> None:
    ctx = detect(_make_request())
    assert ctx.orchestrator_name == "unknown"


def test_register_and_detect() -> None:
    register_adapter(GenericAdapter())
    ctx = detect(_make_request())
    assert ctx.orchestrator_name == "generic"


def test_first_match_wins() -> None:
    register_adapter(ClaudeCodeAdapter())
    register_adapter(GenericAdapter())
    # Claude Code adapter won't match a plain request
    msg = NormalizedMessage(role="user", content="Hello")
    ctx = detect(_make_request(messages=[msg]))
    # Falls through to generic
    assert ctx.orchestrator_name == "generic"


def test_claude_code_detected_before_generic() -> None:
    register_adapter(ClaudeCodeAdapter())
    register_adapter(GenericAdapter())
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="Skill", input={"skill": "commit"})],
    )
    ctx = detect(_make_request(messages=[msg]))
    assert ctx.orchestrator_name == "claude-code"


def test_register_default_adapters() -> None:
    register_default_adapters()
    adapters = get_adapters()
    assert len(adapters) == 2
    assert adapters[0].name == "claude-code"
    assert adapters[1].name == "generic"


def test_register_default_adapters_idempotent() -> None:
    register_default_adapters()
    register_default_adapters()  # should not double-register
    assert len(get_adapters()) == 2


def test_clear_adapters() -> None:
    register_adapter(GenericAdapter())
    assert len(get_adapters()) == 1
    clear_adapters()
    assert len(get_adapters()) == 0


def test_get_adapters_returns_copy() -> None:
    register_adapter(GenericAdapter())
    adapters = get_adapters()
    adapters.clear()
    assert len(get_adapters()) == 1  # original unaffected


def test_detect_empty_messages() -> None:
    register_default_adapters()
    ctx = detect(_make_request(messages=[]))
    assert ctx.orchestrator_name == "generic"


def test_register_default_adapters_with_custom_adapter_present() -> None:
    """Built-ins should be added even when custom adapters are already registered."""

    class CustomAdapter:
        name: str = "custom"

        def detect(self, request: NormalizedRequest) -> DetectedContext | None:  # noqa: ARG002
            return None

    register_adapter(CustomAdapter())  # type: ignore[arg-type]
    register_default_adapters()
    adapters = get_adapters()
    names = [a.name for a in adapters]
    assert "claude-code" in names
    assert "generic" in names
    assert "custom" in names
    assert len(adapters) == 3
    # claude-code should be first (inserted at 0)
    assert names[0] == "claude-code"


def test_detected_context_default_fields() -> None:
    ctx = DetectedContext(orchestrator_name="test")
    assert ctx.skills == []
    assert ctx.tools == []
    assert ctx.agents == []
    assert ctx.system_prompt_source == ""
    assert ctx.request_id is None
