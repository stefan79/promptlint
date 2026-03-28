"""Stage 1: Structural segmentation of prompt text into candidate instruction units."""

from __future__ import annotations

import json
import re

from promptlint.config import Config
from promptlint.models import Chunk

# Patterns
_XML_TAG_OPEN = re.compile(r"<([a-zA-Z][\w-]*)(?:\s[^>]*)?>")
_XML_TAG_CLOSE = re.compile(r"</([a-zA-Z][\w-]*)>")
_MARKDOWN_HEADER = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)
_BULLET = re.compile(r"^(\s*[-*+]\s+|\s*\d+\.\s+)", re.MULTILINE)
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def chunk(text: str, source_section: str = "default", config: Config | None = None) -> list[Chunk]:
    """Split raw prompt text into candidate instruction chunks."""
    if config is None:
        config = Config()

    # Step 1: Extract tool definition blocks first (before any text splitting)
    tool_chunks, text_without_tools = _extract_tool_definitions(text, source_section)

    # Step 2: Split remaining text structurally
    raw_chunks = _split_structural(text_without_tools, source_section, text)

    # Step 3: Apply minimum chunk size merging
    merged = _merge_small_chunks(raw_chunks, config.min_chunk_words)

    return tool_chunks + merged


def _extract_tool_definitions(text: str, source_section: str) -> tuple[list[Chunk], str]:
    """Extract JSON tool definition blocks and return chunks + remaining text."""
    chunks: list[Chunk] = []
    # Look for JSON arrays that look like tool definitions
    # Match patterns like "tools": [...] or standalone [{"name":..., "description":...}]
    remaining = text

    # Try to find tool arrays in the text
    for match in re.finditer(r'"tools"\s*:\s*(\[.*?\])', text, re.DOTALL):
        try:
            tools = json.loads(match.group(1))
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict):
                        # Extract tool-level description
                        desc = tool.get("description", "")
                        if desc:
                            start = text.find(desc, match.start())
                            if start == -1:
                                start = match.start()
                            chunks.append(
                                Chunk(
                                    text=desc,
                                    source_section=f"{source_section}/tool:{tool.get('name', 'unknown')}",
                                    start_offset=start,
                                    end_offset=start + len(desc),
                                    structural_type="tool_desc",
                                )
                            )
                        # Extract parameter-level descriptions with behavioral directives
                        _extract_param_descriptions(tool, source_section, text, match.start(), chunks)
                # Remove the matched tool block from text to avoid double-processing
                remaining = remaining[: match.start()] + " " * len(match.group()) + remaining[match.end() :]
        except (json.JSONDecodeError, TypeError):
            continue

    return chunks, remaining


def _extract_param_descriptions(
    tool: dict, source_section: str, text: str, base_offset: int, chunks: list[Chunk]
) -> None:
    """Extract parameter descriptions that contain behavioral directives."""
    tool_name = tool.get("name", "unknown")
    params = tool.get("input_schema", tool.get("parameters", {}))
    if not isinstance(params, dict):
        return
    properties = params.get("properties", {})
    if not isinstance(properties, dict):
        return
    for param_name, param_def in properties.items():
        if not isinstance(param_def, dict):
            continue
        desc = param_def.get("description", "")
        if desc and _has_directive_language(desc):
            start = text.find(desc, base_offset)
            if start == -1:
                start = base_offset
            chunks.append(
                Chunk(
                    text=desc,
                    source_section=f"{source_section}/tool:{tool_name}/param:{param_name}",
                    start_offset=start,
                    end_offset=start + len(desc),
                    structural_type="tool_desc",
                )
            )


def _has_directive_language(text: str) -> bool:
    """Check if text contains directive language (modal verbs, imperatives)."""
    lower = text.lower()
    return any(word in lower for word in ("must", "should", "shall", "never", "always", "do not", "cannot", "required"))


def _split_structural(text: str, source_section: str, original_text: str) -> list[Chunk]:
    """Apply hierarchical structural splitting rules."""
    # Try XML splitting first
    xml_segments = _split_xml(text, source_section, original_text)
    if xml_segments is not None:
        # XML structure found — recurse into each segment's content
        result: list[Chunk] = []
        for seg_text, seg_section, seg_offset, seg_type in xml_segments:
            if seg_type == "xml_block":
                # Recurse into XML content (may contain markdown, bullets, etc.)
                sub_chunks = _split_non_xml(seg_text, seg_section, seg_offset, original_text)
                result.extend(sub_chunks)
            else:
                result.extend(_split_non_xml(seg_text, seg_section, seg_offset, original_text))
        return result

    # No XML structure — use markdown/bullet/paragraph splitting
    base_offset = original_text.find(text)
    if base_offset == -1:
        base_offset = 0
    return _split_non_xml(text, source_section, base_offset, original_text)


def _split_xml(text: str, source_section: str, original_text: str) -> list[tuple[str, str, int, str]] | None:
    """Split on XML tags. Returns None if no XML structure found."""
    open_tags = list(_XML_TAG_OPEN.finditer(text))
    close_tags = list(_XML_TAG_CLOSE.finditer(text))

    if not open_tags and not close_tags:
        return None

    base_offset = original_text.find(text)
    if base_offset == -1:
        base_offset = 0

    segments: list[tuple[str, str, int, str]] = []
    pos = 0

    # Simple approach: find matching open/close tag pairs
    tag_events: list[tuple[int, str, str, bool]] = []  # (pos, tag_name, full_match, is_open)
    for m in open_tags:
        tag_events.append((m.start(), m.group(1), m.group(), True))
    for m in close_tags:
        tag_events.append((m.start(), m.group(1), m.group(), False))
    tag_events.sort(key=lambda x: x[0])

    stack: list[tuple[str, int, int]] = []  # (tag_name, content_start, tag_start)

    for event_pos, tag_name, full_match, is_open in tag_events:
        if is_open:
            # Capture text before this tag
            if event_pos > pos and not stack:
                before = text[pos:event_pos].strip()
                if before:
                    segments.append((before, source_section, base_offset + pos, "paragraph"))
            content_start = event_pos + len(full_match)
            stack.append((tag_name, content_start, event_pos))
        elif stack and stack[-1][0] == tag_name:
            _, content_start, _ = stack.pop()
            content = text[content_start:event_pos].strip()
            if content:
                section = f"{source_section}/{tag_name}"
                segments.append((content, section, base_offset + content_start, "xml_block"))
            pos = event_pos + len(full_match)

    # Capture trailing text
    if pos < len(text) and not stack:
        trailing = text[pos:].strip()
        if trailing:
            segments.append((trailing, source_section, base_offset + pos, "paragraph"))

    return segments if segments else None


def _split_non_xml(text: str, source_section: str, base_offset: int, original_text: str) -> list[Chunk]:
    """Split text using markdown headers, bullets, paragraphs, and semicolons."""
    # Step 1: Split on markdown headers
    header_segments = _split_markdown_headers(text, source_section, base_offset)

    result: list[Chunk] = []
    for seg_text, seg_section, seg_offset, seg_type in header_segments:
        # Step 2: Split on bullets/numbered lists
        bullet_segments = _split_bullets(seg_text, seg_section, seg_offset, seg_type)

        for b_text, b_section, b_offset, b_type in bullet_segments:
            # Step 3: Split on paragraph breaks
            para_segments = _split_paragraphs(b_text, b_section, b_offset, b_type)

            for p_text, p_section, p_offset, p_type in para_segments:
                # Step 4: Split on semicolons
                semi_chunks = _split_semicolons(p_text, p_section, p_offset, p_type)
                result.extend(semi_chunks)

    return result


def _split_markdown_headers(text: str, source_section: str, base_offset: int) -> list[tuple[str, str, int, str]]:
    """Split on markdown headers."""
    matches = list(_MARKDOWN_HEADER.finditer(text))
    if not matches:
        stripped = text.strip()
        if stripped:
            return [(stripped, source_section, base_offset, "paragraph")]
        return []

    segments: list[tuple[str, str, int, str]] = []

    # Text before first header
    if matches[0].start() > 0:
        before = text[: matches[0].start()].strip()
        if before:
            segments.append((before, source_section, base_offset, "paragraph"))

    for i, m in enumerate(matches):
        header_text = m.group(2).strip()
        section_name = f"{source_section}/{header_text}"
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        if content:
            segments.append((content, section_name, base_offset + content_start, "header_content"))

    return segments


def _split_bullets(
    text: str, source_section: str, base_offset: int, structural_type: str
) -> list[tuple[str, str, int, str]]:
    """Split on bullet points and numbered lists."""
    matches = list(_BULLET.finditer(text))
    if not matches:
        stripped = text.strip()
        if stripped:
            return [(stripped, source_section, base_offset, structural_type)]
        return []

    segments: list[tuple[str, str, int, str]] = []

    # Text before first bullet
    if matches[0].start() > 0:
        before = text[: matches[0].start()].strip()
        if before:
            segments.append((before, source_section, base_offset, structural_type))

    for i, m in enumerate(matches):
        item_start = m.end()
        item_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        item_text = text[item_start:item_end].strip()
        if item_text:
            segments.append((item_text, source_section, base_offset + item_start, "bullet"))

    return segments


def _split_paragraphs(
    text: str, source_section: str, base_offset: int, structural_type: str
) -> list[tuple[str, str, int, str]]:
    """Split on paragraph breaks (double newlines)."""
    parts = _PARAGRAPH_BREAK.split(text)
    if len(parts) <= 1:
        stripped = text.strip()
        if stripped:
            return [(stripped, source_section, base_offset, structural_type)]
        return []

    segments: list[tuple[str, str, int, str]] = []
    pos = 0
    for part in parts:
        stripped = part.strip()
        if stripped:
            # Find actual position in text
            idx = text.find(part, pos)
            if idx == -1:
                idx = pos
            segments.append((stripped, source_section, base_offset + idx, structural_type))
            pos = idx + len(part)

    return segments


def _split_semicolons(text: str, source_section: str, base_offset: int, structural_type: str) -> list[Chunk]:
    """Split on semicolons unconditionally."""
    parts = text.split(";")
    if len(parts) <= 1:
        stripped = text.strip()
        if stripped:
            return [
                Chunk(
                    text=stripped,
                    source_section=source_section,
                    start_offset=base_offset,
                    end_offset=base_offset + len(text),
                    structural_type=structural_type,
                )
            ]
        return []

    chunks: list[Chunk] = []
    pos = 0
    for part in parts:
        stripped = part.strip()
        if stripped:
            idx = text.find(part, pos)
            if idx == -1:
                idx = pos
            chunks.append(
                Chunk(
                    text=stripped,
                    source_section=source_section,
                    start_offset=base_offset + idx,
                    end_offset=base_offset + idx + len(part.rstrip()),
                    structural_type=structural_type,
                )
            )
            pos = idx + len(part)

    return chunks


def _merge_small_chunks(chunks: list[Chunk], min_words: int) -> list[Chunk]:
    """Merge chunks shorter than min_words with their nearest neighbor."""
    if not chunks:
        return []
    if len(chunks) == 1:
        return chunks

    result: list[Chunk] = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        word_count = len(c.text.split())
        if word_count < min_words and result:
            # Merge with previous chunk
            prev = result[-1]
            result[-1] = Chunk(
                text=prev.text + " " + c.text,
                source_section=prev.source_section,
                start_offset=prev.start_offset,
                end_offset=c.end_offset,
                structural_type=prev.structural_type,
            )
        elif word_count < min_words and i + 1 < len(chunks):
            # Merge with next chunk
            nxt = chunks[i + 1]
            chunks[i + 1] = Chunk(
                text=c.text + " " + nxt.text,
                source_section=nxt.source_section,
                start_offset=c.start_offset,
                end_offset=nxt.end_offset,
                structural_type=nxt.structural_type,
            )
        else:
            result.append(c)
        i += 1

    return result
