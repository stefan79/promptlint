"""Generic orchestrator adapter — fallback for unrecognized orchestrators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from promptlint.orchestrators import DetectedContext, ToolInfo

if TYPE_CHECKING:
    from promptlint.gateways.normalizer import NormalizedRequest

# Map vendor to how the system prompt is extracted
_VENDOR_SYSTEM_SOURCES: dict[str, str] = {
    "anthropic": "body.system",
    "openai": "messages[0]",
    "gemini": "body.system_instruction",
}


class GenericAdapter:
    name: str = "generic"

    def detect(self, request: NormalizedRequest) -> DetectedContext:
        """Always matches — returns generic context with tool extraction."""
        tools = extract_tools(request)
        system_source = _VENDOR_SYSTEM_SOURCES.get(request.vendor, "unknown")

        return DetectedContext(
            orchestrator_name="generic",
            tools=tools,
            system_prompt_source=system_source,
        )


def extract_tools(request: NormalizedRequest) -> list[ToolInfo]:
    """Extract tool definitions from normalized request (vendor-agnostic)."""
    tools: list[ToolInfo] = []
    for tool_def in request.tools:
        name = _extract_tool_name(tool_def)
        if not name:
            continue
        param_count = _count_params(tool_def)
        tools.append(ToolInfo(name=name, param_count=param_count))
    return tools


def _extract_tool_name(tool_def: dict[str, object]) -> str:
    """Extract tool name from various vendor formats."""
    # Anthropic: {"name": "..."}
    name = tool_def.get("name")
    if name:
        return str(name)
    # OpenAI: {"function": {"name": "..."}}
    func = tool_def.get("function")
    if isinstance(func, dict):
        fname = func.get("name")
        if fname:
            return str(fname)
    return ""


def _count_params(tool_def: dict[str, object]) -> int:
    """Count parameters from various vendor tool schemas."""
    # Anthropic: input_schema.properties
    schema = tool_def.get("input_schema")
    if isinstance(schema, dict):
        props = schema.get("properties")
        if isinstance(props, dict):
            return len(props)

    # OpenAI: function.parameters.properties
    func = tool_def.get("function")
    if isinstance(func, dict):
        params = func.get("parameters")
        if isinstance(params, dict):
            props = params.get("properties")
            if isinstance(props, dict):
                return len(props)

    # Gemini: parameters.properties (function_declarations format)
    params = tool_def.get("parameters")
    if isinstance(params, dict):
        props = params.get("properties")
        if isinstance(props, dict):
            return len(props)

    return 0
