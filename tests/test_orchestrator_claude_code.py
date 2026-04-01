from promptlint.gateways.normalizer import NormalizedMessage, NormalizedRequest, ToolCall
from promptlint.orchestrators.claude_code import ClaudeCodeAdapter


def _make_request(
    messages: list[NormalizedMessage] | None = None,
    system_prompt: str | None = None,
    tools: list[dict[str, object]] | None = None,
) -> NormalizedRequest:
    return NormalizedRequest(
        vendor="anthropic",
        system_prompt=system_prompt,
        tools=tools or [],
        messages=messages or [],
        raw_body=b"{}",
        model_id="claude-sonnet-4-20250514",
    )


def test_detect_skill_invocation() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="Skill", input={"skill": "commit"})],
    )
    request = _make_request(messages=[msg], system_prompt="You are an AI assistant.")
    ctx = adapter.detect(request)
    assert ctx is not None
    assert ctx.orchestrator_name == "claude-code"
    assert len(ctx.skills) == 1
    assert ctx.skills[0].name == "commit"
    assert ctx.skills[0].source == "passive"
    assert ctx.system_prompt_source == "body.system"


def test_detect_multiple_skills() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(name="Skill", input={"skill": "commit"}),
            ToolCall(name="Skill", input={"skill": "review-pr"}),
        ],
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is not None
    assert [s.name for s in ctx.skills] == ["commit", "review-pr"]


def test_detect_agent_launch() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="Agent", input={"subagent_type": "parallel"})],
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is not None
    assert len(ctx.agents) == 1
    assert ctx.agents[0].name == "parallel"
    assert ctx.agents[0].agent_type == "parallel"


def test_detect_agent_default_type() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="Agent", input={})],
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is not None
    assert ctx.agents[0].agent_type == "agent"


def test_detect_system_reminder_tags() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="user",
        content="<system-reminder>Some context here</system-reminder>",
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is not None
    assert ctx.orchestrator_name == "claude-code"


def test_detect_system_reminder_multiline() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="user",
        content="Hello\n<system-reminder>\nMultiline\ncontent\n</system-reminder>\nBye",
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is not None


def test_no_match_plain_anthropic_request() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(role="user", content="Hello world")
    ctx = adapter.detect(_make_request(messages=[msg], system_prompt="Be helpful"))
    assert ctx is None


def test_no_match_empty_messages() -> None:
    adapter = ClaudeCodeAdapter()
    ctx = adapter.detect(_make_request(messages=[]))
    assert ctx is None


def test_no_match_non_skill_tool_calls() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="Read", input={"file_path": "/tmp/foo"})],
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is None


def test_skill_with_empty_name_ignored() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="assistant",
        content="<system-reminder>ctx</system-reminder>",
        tool_calls=[ToolCall(name="Skill", input={"skill": ""})],
    )
    ctx = adapter.detect(_make_request(messages=[msg]))
    assert ctx is not None
    # Empty skill name is not added to skills list
    assert len(ctx.skills) == 0


def test_tool_extraction_from_request() -> None:
    adapter = ClaudeCodeAdapter()
    tools: list[dict[str, object]] = [
        {
            "name": "Read",
            "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}},
        },
        {
            "name": "Edit",
            "input_schema": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}, "old_string": {"type": "string"}},
            },
        },
    ]
    msg = NormalizedMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(name="Skill", input={"skill": "commit"})],
    )
    ctx = adapter.detect(_make_request(messages=[msg], tools=tools))
    assert ctx is not None
    assert len(ctx.tools) == 2
    assert ctx.tools[0].name == "Read"
    assert ctx.tools[0].param_count == 1
    assert ctx.tools[1].name == "Edit"
    assert ctx.tools[1].param_count == 2


def test_tool_with_no_name_skipped() -> None:
    adapter = ClaudeCodeAdapter()
    tools: list[dict[str, object]] = [{"input_schema": {"type": "object", "properties": {}}}]
    msg = NormalizedMessage(
        role="user",
        content="<system-reminder>x</system-reminder>",
    )
    ctx = adapter.detect(_make_request(messages=[msg], tools=tools))
    assert ctx is not None
    assert len(ctx.tools) == 0


def test_tool_with_no_schema() -> None:
    adapter = ClaudeCodeAdapter()
    tools: list[dict[str, object]] = [{"name": "Simple"}]
    msg = NormalizedMessage(
        role="user",
        content="<system-reminder>x</system-reminder>",
    )
    ctx = adapter.detect(_make_request(messages=[msg], tools=tools))
    assert ctx is not None
    assert ctx.tools[0].param_count == 0


def test_mixed_skills_and_agents() -> None:
    adapter = ClaudeCodeAdapter()
    messages = [
        NormalizedMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(name="Skill", input={"skill": "architect"}),
                ToolCall(name="Agent", input={"subagent_type": "parallel"}),
                ToolCall(name="Skill", input={"skill": "test-rules"}),
            ],
        ),
    ]
    ctx = adapter.detect(_make_request(messages=messages))
    assert ctx is not None
    assert [s.name for s in ctx.skills] == ["architect", "test-rules"]
    assert [a.name for a in ctx.agents] == ["parallel"]


def test_no_system_prompt_source_empty() -> None:
    adapter = ClaudeCodeAdapter()
    msg = NormalizedMessage(
        role="user",
        content="<system-reminder>x</system-reminder>",
    )
    ctx = adapter.detect(_make_request(messages=[msg], system_prompt=None))
    assert ctx is not None
    assert ctx.system_prompt_source == ""
