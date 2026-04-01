"""Claude Code passive detection adapter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from promptlint.orchestrators import AgentInfo, DetectedContext, SkillInfo
from promptlint.orchestrators.generic import extract_tools

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
            if not has_system_reminder and msg.content and SYSTEM_REMINDER_RE.search(msg.content):
                has_system_reminder = True

        # Only match if we found Claude Code signals
        if not skills and not agents and not has_system_reminder:
            return None

        tools = extract_tools(request)

        return DetectedContext(
            orchestrator_name="claude-code",
            skills=skills,
            tools=tools,
            agents=agents,
            system_prompt_source="body.system" if request.system_prompt is not None else "",
        )
