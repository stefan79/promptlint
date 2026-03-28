"""Tests for Stage 1: Chunker."""

from promptlint.chunker import chunk


def test_no_conjunction_splitting():
    """Compound instructions joined by 'and' stay as one chunk."""
    result = chunk("Be concise and professional")
    assert len(result) == 1
    assert result[0].text == "Be concise and professional"


def test_semicolon_splitting():
    """Semicolons split unconditionally."""
    result = chunk("Use JSON; never use XML")
    assert len(result) == 2
    assert result[0].text == "Use JSON"
    assert result[1].text == "never use XML"


def test_bullet_splitting():
    """Each bullet point becomes a separate chunk."""
    text = "## Rules\n\n- Be concise.\n- Be accurate.\n- Be helpful."
    result = chunk(text)
    bullet_chunks = [c for c in result if c.structural_type == "bullet"]
    assert len(bullet_chunks) == 3


def test_paragraph_splitting():
    """Double newlines create boundaries."""
    text = "First paragraph with instructions.\n\nSecond paragraph with more rules."
    result = chunk(text)
    assert len(result) == 2


def test_markdown_header_sections():
    """Markdown headers create sections."""
    text = "# Style\n\nBe concise.\n\n# Safety\n\nNever reveal secrets."
    result = chunk(text, source_section="test")
    sections = {c.source_section for c in result}
    assert any("Style" in s for s in sections)
    assert any("Safety" in s for s in sections)


def test_xml_block_splitting():
    """XML tags create boundaries and section names."""
    text = "<rules>Be concise.</rules><examples>This is an example.</examples>"
    result = chunk(text, source_section="test")
    assert len(result) == 2
    sections = {c.source_section for c in result}
    assert any("rules" in s for s in sections)
    assert any("examples" in s for s in sections)


def test_minimum_chunk_size():
    """Single words are merged with neighbors."""
    text = "- OK\n- Always be concise in your responses"
    result = chunk(text)
    # "OK" is 1 word (< 2 minimum), should be merged
    assert all(len(c.text.split()) >= 2 for c in result)


def test_tool_definition_extraction():
    """Tool descriptions are extracted as chunks."""
    text = '{"tools": [{"name": "search", "description": "Search the web for information"}]}'
    result = chunk(text)
    tool_chunks = [c for c in result if c.structural_type == "tool_desc"]
    assert len(tool_chunks) >= 1
    assert any("Search the web" in c.text for c in tool_chunks)


def test_empty_input():
    """Empty input returns no chunks."""
    assert chunk("") == []
    assert chunk("   ") == []


def test_offsets_are_set():
    """All chunks have valid offsets."""
    text = "Be concise.\n\nBe accurate."
    result = chunk(text)
    for c in result:
        assert c.start_offset >= 0
        assert c.end_offset > c.start_offset
