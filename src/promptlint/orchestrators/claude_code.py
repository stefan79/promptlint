"""Claude Code passive detection adapter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from promptlint.orchestrators import AgentInfo, DetectedContext, SkillInfo, ToolInfo

if TYPE_CHECKING:
    from promptlint.gateways.normalizer import NormalizedRequest

SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>(.*?)</system-reminder>", re.DOTALL)


class ClaudeCodeAdapter:
    name: str = "claude-code"

    def detect(self, request: NormalizedRequest) -> DetectedContext | None:
        """Detect Claude Code patterns in the normalized request."""
        skills: list[SkillInfo] = []
        agents: list[AgentInfo] = []
        has_system_reminder = False

        for msg in request.messages:
            # Check tool calls for Skill/Agent invocations
            for tc in msg.tool_calls:
                inp = tc.input if isinstance(tc.input, dict) else {}
                if tc.name == "Skill":
                    skill_name = inp.get("skill", "")
                    if skill_name:
                        skills.append(SkillInfo(name=str(skill_name)))
                elif tc.name == "Agent":
                    agent_type = str(inp.get("subagent_type", "agent"))
                    agents.append(AgentInfo(name=agent_type, agent_type=agent_type))

            # Check message content for system-reminder tags
            if msg.content and SYSTEM_REMINDER_RE.search(msg.content):
                has_system_reminder = True

        # Only match if we found Claude Code signals
        if not skills and not agents and not has_system_reminder:
            return None

        tools = _extract_tools(request)

        return DetectedContext(
            orchestrator_name="claude-code",
            skills=skills,
            tools=tools,
            agents=agents,
            system_prompt_source="body.system" if request.system_prompt is not None else "",
        )


def _extract_tools(request: NormalizedRequest) -> list[ToolInfo]:
    """Extract tool definitions from the normalized request."""
    tools: list[ToolInfo] = []
    for tool_def in request.tools:
        name = str(tool_def.get("name", ""))
        if not name:
            continue
        # Count parameters from input_schema (Anthropic format)
        param_count = 0
        schema = tool_def.get("input_schema")
        if isinstance(schema, dict):
            props = schema.get("properties")
            if isinstance(props, dict):
                param_count = len(props)
        tools.append(ToolInfo(name=name, param_count=param_count))
    return tools
