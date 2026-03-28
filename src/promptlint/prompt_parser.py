"""Input parsing: raw string, structured, and file-based prompt formats."""

from __future__ import annotations

import json
from pathlib import Path

from promptlint.chunker import chunk
from promptlint.config import Config
from promptlint.models import Chunk


def parse_raw(text: str, config: Config | None = None) -> list[Chunk]:
    """Parse a raw prompt string into chunks."""
    return chunk(text, source_section="raw", config=config)


def parse_structured(
    system_prompt: str | None = None,
    skills: list[str] | None = None,
    constitution: str | None = None,
    tools: list[dict] | None = None,
    user_message: str | None = None,
    config: Config | None = None,
) -> list[Chunk]:
    """Parse a structured prompt with named sections into chunks."""
    all_chunks: list[Chunk] = []

    if system_prompt:
        all_chunks.extend(chunk(system_prompt, source_section="system_prompt", config=config))

    if skills:
        for i, skill_content in enumerate(skills):
            all_chunks.extend(chunk(skill_content, source_section=f"skill_{i}", config=config))

    if constitution:
        all_chunks.extend(chunk(constitution, source_section="constitution", config=config))

    if tools:
        # Wrap tools in a JSON structure so the chunker can extract them
        tools_json = json.dumps({"tools": tools})
        all_chunks.extend(chunk(tools_json, source_section="tools", config=config))

    if user_message:
        all_chunks.extend(chunk(user_message, source_section="user_message", config=config))

    return all_chunks


def parse_files(
    claude_md: str | None = None,
    skill_dirs: list[str] | None = None,
    system_prompt: str | None = None,
    config: Config | None = None,
) -> list[Chunk]:
    """Parse prompt files from disk into chunks."""
    system_text = None
    skills_texts: list[str] = []

    if system_prompt:
        system_text = Path(system_prompt).read_text()

    if claude_md:
        claude_text = Path(claude_md).read_text()
        # Treat CLAUDE.md as a system prompt section if no system_prompt given
        if system_text is None:
            system_text = claude_text
        else:
            system_text = claude_text + "\n\n" + system_text

    if skill_dirs:
        for skill_dir in skill_dirs:
            skill_path = Path(skill_dir)
            if skill_path.is_dir():
                for f in sorted(skill_path.rglob("*.md")):
                    skills_texts.append(f.read_text())
                for f in sorted(skill_path.rglob("*.txt")):
                    skills_texts.append(f.read_text())

    return parse_structured(
        system_prompt=system_text,
        skills=skills_texts if skills_texts else None,
        config=config,
    )
