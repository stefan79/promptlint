"""Tests for vendor detection and request normalization."""

from __future__ import annotations

import json

import pytest

from promptlint.gateways import VendorDetectionError
from promptlint.gateways.normalizer import (
    detect_vendor,
    normalize,
)

# --- Vendor detection ---


def test_detect_anthropic_with_system_key() -> None:
    body = {"system": "You are helpful.", "messages": [], "max_tokens": 1024}
    assert detect_vendor(body) == "anthropic"


def test_detect_anthropic_with_max_tokens() -> None:
    body = {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 512}
    assert detect_vendor(body) == "anthropic"


def test_detect_openai_simple() -> None:
    body = {"messages": [{"role": "user", "content": "Hi"}], "model": "gpt-4o"}
    assert detect_vendor(body) == "openai"


def test_detect_openai_with_max_completion_tokens() -> None:
    body = {"messages": [{"role": "user", "content": "Hi"}], "max_completion_tokens": 1024}
    assert detect_vendor(body) == "openai"


def test_detect_gemini_system_instruction() -> None:
    body = {"system_instruction": {"parts": [{"text": "Be helpful"}]}, "contents": []}
    assert detect_vendor(body) == "gemini"


def test_detect_gemini_contents_without_messages() -> None:
    body = {"contents": [{"role": "user", "parts": [{"text": "Hi"}]}]}
    assert detect_vendor(body) == "gemini"


def test_detect_unknown_raises() -> None:
    with pytest.raises(VendorDetectionError):
        detect_vendor({})


def test_detect_unknown_no_messages_raises() -> None:
    with pytest.raises(VendorDetectionError):
        detect_vendor({"model": "gpt-4o"})


# --- Anthropic normalization ---


def test_normalize_anthropic_string_system() -> None:
    body = {"system": "Be concise.", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 100}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.vendor == "anthropic"
    assert result.system_prompt == "Be concise."
    assert len(result.messages) == 1
    assert result.messages[0].role == "user"
    assert result.messages[0].content == "Hello"


def test_normalize_anthropic_content_block_system() -> None:
    body = {
        "system": [{"type": "text", "text": "Part 1"}, {"type": "text", "text": "Part 2"}],
        "messages": [],
        "max_tokens": 100,
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.system_prompt == "Part 1\n\nPart 2"


def test_normalize_anthropic_no_system() -> None:
    body = {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.system_prompt is None


def test_normalize_anthropic_tool_use_messages() -> None:
    body = {
        "system": "sys",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "commit"}},
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "content": "skill content here"}],
            },
        ],
        "max_tokens": 100,
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert len(result.messages) == 2
    assert result.messages[0].tool_calls[0].name == "Skill"
    assert result.messages[0].tool_calls[0].input == {"skill": "commit"}
    assert "skill content here" in result.messages[1].content


def test_normalize_anthropic_tools() -> None:
    body = {
        "system": "sys",
        "messages": [],
        "tools": [{"name": "read_file", "description": "Read a file", "input_schema": {}}],
        "max_tokens": 100,
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert len(result.tools) == 1
    assert result.tools[0]["name"] == "read_file"


def test_normalize_anthropic_model_id() -> None:
    body = {"system": "sys", "messages": [], "model": "claude-sonnet-4-20250514", "max_tokens": 100}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.model_id == "claude-sonnet-4-20250514"


# --- OpenAI normalization ---


def test_normalize_openai_system_message() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hi"},
        ],
        "model": "gpt-4o",
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.vendor == "openai"
    assert result.system_prompt == "You are a helpful assistant."
    assert len(result.messages) == 1
    assert result.messages[0].role == "user"


def test_normalize_openai_no_system() -> None:
    body = {"messages": [{"role": "user", "content": "Hi"}], "model": "gpt-4o"}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.system_prompt is None
    assert len(result.messages) == 1


def test_normalize_openai_tool_calls() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"type": "function", "function": {"name": "get_weather", "arguments": '{"city": "SF"}'}},
                ],
            },
        ],
        "model": "gpt-4o",
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert len(result.messages) == 1
    assert result.messages[0].tool_calls[0].name == "get_weather"
    assert result.messages[0].tool_calls[0].input == {"city": "SF"}


def test_normalize_openai_tools() -> None:
    body = {
        "messages": [{"role": "user", "content": "Hi"}],
        "tools": [{"type": "function", "function": {"name": "calc", "parameters": {}}}],
        "model": "gpt-4o",
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert len(result.tools) == 1


# --- Gemini normalization ---


def test_normalize_gemini_basic() -> None:
    body = {
        "system_instruction": {"parts": [{"text": "Be helpful"}]},
        "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.vendor == "gemini"
    assert result.system_prompt == "Be helpful"
    assert len(result.messages) == 1
    assert result.messages[0].content == "Hello"


def test_normalize_gemini_multi_part_system() -> None:
    body = {
        "system_instruction": {"parts": [{"text": "Part A"}, {"text": "Part B"}]},
        "contents": [],
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.system_prompt == "Part A\n\nPart B"


def test_normalize_gemini_tools() -> None:
    body = {
        "system_instruction": {"parts": [{"text": "sys"}]},
        "contents": [],
        "tools": [{"function_declarations": [{"name": "search", "description": "Search the web"}]}],
    }
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert len(result.tools) == 1
    assert result.tools[0]["name"] == "search"


def test_normalize_gemini_no_system() -> None:
    body = {"contents": [{"role": "user", "parts": [{"text": "Hi"}]}]}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.system_prompt is None


# --- Vendor override ---


def test_vendor_override_skips_detection() -> None:
    body = {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 100}
    raw = json.dumps(body).encode()
    result = normalize(raw, vendor_override="openai")
    assert result.vendor == "openai"
    # max_tokens would normally detect as anthropic, but override forces openai
    assert result.system_prompt is None


def test_unsupported_vendor_override_raises() -> None:
    body = {"messages": []}
    raw = json.dumps(body).encode()
    with pytest.raises(VendorDetectionError, match="Unsupported vendor"):
        normalize(raw, vendor_override="mistral")


# --- Edge cases ---


def test_normalize_empty_messages() -> None:
    body = {"system": "sys", "messages": [], "max_tokens": 100}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.messages == []


def test_normalize_preserves_raw_body() -> None:
    body = {"system": "sys", "messages": [], "max_tokens": 100}
    raw = json.dumps(body).encode()
    result = normalize(raw)
    assert result.raw_body == raw


def test_normalize_malformed_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        normalize(b"not json")
