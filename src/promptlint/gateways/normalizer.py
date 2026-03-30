"""Vendor-specific request normalization for Anthropic, OpenAI, and Gemini APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from promptlint.gateways import VendorDetectionError


@dataclass
class ToolCall:
    name: str
    input: dict[str, object]
    output: str | None = None


@dataclass
class NormalizedMessage:
    role: str  # "user", "assistant", "system", "tool_result"
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class NormalizedRequest:
    vendor: str  # "anthropic", "openai", "gemini"
    system_prompt: str | None
    tools: list[dict[str, object]]
    messages: list[NormalizedMessage]
    raw_body: bytes
    model_id: str | None = None
    orchestrator_context: object | None = None  # OrchestratorContext when spec 08 lands


def detect_vendor(body: dict[str, object]) -> str:
    """Detect vendor from top-level keys in the request body."""
    if "system_instruction" in body or ("contents" in body and "messages" not in body):
        return "gemini"
    if "system" in body:
        return "anthropic"
    if "messages" in body:
        return "openai"
    msg = f"Cannot determine vendor from request body keys: {sorted(body.keys())}"
    raise VendorDetectionError(msg)


def normalize(raw_body: bytes, vendor_override: str | None = None) -> NormalizedRequest:
    """Parse raw bytes and produce a NormalizedRequest."""
    body = json.loads(raw_body)
    vendor = vendor_override or detect_vendor(body)
    if vendor == "anthropic":
        return _normalize_anthropic(body, raw_body)
    if vendor == "openai":
        return _normalize_openai(body, raw_body)
    if vendor == "gemini":
        return _normalize_gemini(body, raw_body)
    msg = f"Unsupported vendor: {vendor}"
    raise VendorDetectionError(msg)


def _normalize_anthropic(body: dict[str, object], raw_body: bytes) -> NormalizedRequest:
    system_prompt = _extract_anthropic_system(body.get("system"))
    tools = _as_list_of_dicts(body.get("tools", []))
    raw_messages = _as_list_of_dicts(body.get("messages", []))
    messages = [_convert_anthropic_message(m) for m in raw_messages]
    model_id = body.get("model")
    return NormalizedRequest(
        vendor="anthropic",
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
        raw_body=raw_body,
        model_id=str(model_id) if model_id else None,
    )


def _extract_anthropic_system(system: object) -> str | None:
    if system is None:
        return None
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts = []
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n\n".join(parts) if parts else None
    return None


def _convert_anthropic_message(msg: dict[str, object]) -> NormalizedMessage:
    role = str(msg.get("role", "user"))
    content = msg.get("content", "")
    if isinstance(content, str):
        return NormalizedMessage(role=role, content=content)
    # Content blocks
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(str(block.get("text", "")))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        name=str(block.get("name", "")),
                        input=block.get("input", {}),  # type: ignore[arg-type]
                    )
                )
            elif block_type == "tool_result":
                tc_content = block.get("content", "")
                text_parts.append(str(tc_content) if tc_content else "")
    return NormalizedMessage(role=role, content="\n".join(text_parts), tool_calls=tool_calls)


def _normalize_openai(body: dict[str, object], raw_body: bytes) -> NormalizedRequest:
    raw_messages = _as_list_of_dicts(body.get("messages", []))
    system_prompt: str | None = None
    messages: list[NormalizedMessage] = []
    for msg in raw_messages:
        role = str(msg.get("role", "user"))
        if role == "system" and system_prompt is None:
            system_prompt = str(msg.get("content", ""))
            continue
        content = str(msg.get("content", ""))
        tool_calls = _extract_openai_tool_calls(msg)
        messages.append(NormalizedMessage(role=role, content=content, tool_calls=tool_calls))
    tools = _as_list_of_dicts(body.get("tools", []))
    model_id = body.get("model")
    return NormalizedRequest(
        vendor="openai",
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
        raw_body=raw_body,
        model_id=str(model_id) if model_id else None,
    )


def _extract_openai_tool_calls(msg: dict[str, object]) -> list[ToolCall]:
    raw_calls = msg.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[ToolCall] = []
    for tc in raw_calls:
        if not isinstance(tc, dict):
            continue
        func = tc.get("function", {})
        if isinstance(func, dict):
            name = str(func.get("name", ""))
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(str(args_str))
            except (json.JSONDecodeError, TypeError):
                args = {}
            calls.append(ToolCall(name=name, input=args))
    return calls


def _normalize_gemini(body: dict[str, object], raw_body: bytes) -> NormalizedRequest:
    system_prompt = _extract_gemini_system(body.get("system_instruction"))
    tools = _extract_gemini_tools(body.get("tools"))
    raw_contents = body.get("contents", [])
    messages: list[NormalizedMessage] = []
    if isinstance(raw_contents, list):
        for item in raw_contents:
            if isinstance(item, dict):
                messages.append(_convert_gemini_content(item))
    model_id = body.get("model")
    return NormalizedRequest(
        vendor="gemini",
        system_prompt=system_prompt,
        tools=tools,
        messages=messages,
        raw_body=raw_body,
        model_id=str(model_id) if model_id else None,
    )


def _extract_gemini_system(system_instruction: object) -> str | None:
    if not isinstance(system_instruction, dict):
        return None
    parts = system_instruction.get("parts", [])
    if not isinstance(parts, list):
        return None
    texts = [str(p.get("text", "")) for p in parts if isinstance(p, dict) and "text" in p]
    return "\n\n".join(texts) if texts else None


def _extract_gemini_tools(tools: object) -> list[dict[str, object]]:
    if not isinstance(tools, list) or not tools:
        return []
    first = tools[0]
    if isinstance(first, dict) and "function_declarations" in first:
        decls = first["function_declarations"]
        if isinstance(decls, list):
            return decls  # type: ignore[return-value]
    return []


def _convert_gemini_content(item: dict[str, object]) -> NormalizedMessage:
    role = str(item.get("role", "user"))
    parts = item.get("parts", [])
    text_parts: list[str] = []
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, dict) and "text" in p:
                text_parts.append(str(p["text"]))
    return NormalizedMessage(role=role, content="\n".join(text_parts))


def _as_list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
