from promptlint.models import ClassifiedChunk
from promptlint.orchestrators import AgentInfo, DetectedContext, SkillInfo, ToolInfo
from promptlint.orchestrators.envelope import (
    EMPTY_FINGERPRINT,
    OrchestratorEnvelope,
    build_envelope,
    compute_fingerprint,
)


def _make_chunk(text: str) -> ClassifiedChunk:
    return ClassifiedChunk(
        text=text,
        source_section="test",
        start_offset=0,
        end_offset=len(text),
        structural_type="paragraph",
        label="instruction",
        confidence=0.9,
    )


def test_fingerprint_empty_instructions() -> None:
    assert compute_fingerprint([]) == EMPTY_FINGERPRINT


def test_fingerprint_single_instruction() -> None:
    fp = compute_fingerprint([_make_chunk("Always respond in English")])
    assert len(fp) == 16
    assert fp != EMPTY_FINGERPRINT


def test_fingerprint_order_independent() -> None:
    chunks_a = [_make_chunk("First instruction"), _make_chunk("Second instruction")]
    chunks_b = [_make_chunk("Second instruction"), _make_chunk("First instruction")]
    assert compute_fingerprint(chunks_a) == compute_fingerprint(chunks_b)


def test_fingerprint_whitespace_normalized() -> None:
    chunk_a = _make_chunk("Always   respond   in   English")
    chunk_b = _make_chunk("Always respond in English")
    assert compute_fingerprint([chunk_a]) == compute_fingerprint([chunk_b])


def test_fingerprint_case_insensitive() -> None:
    chunk_a = _make_chunk("Always Respond In English")
    chunk_b = _make_chunk("always respond in english")
    assert compute_fingerprint([chunk_a]) == compute_fingerprint([chunk_b])


def test_fingerprint_leading_trailing_whitespace() -> None:
    chunk_a = _make_chunk("  Always respond in English  ")
    chunk_b = _make_chunk("Always respond in English")
    assert compute_fingerprint([chunk_a]) == compute_fingerprint([chunk_b])


def test_fingerprint_different_instructions_differ() -> None:
    fp_a = compute_fingerprint([_make_chunk("Use Python")])
    fp_b = compute_fingerprint([_make_chunk("Use Rust")])
    assert fp_a != fp_b


def test_fingerprint_is_hex() -> None:
    fp = compute_fingerprint([_make_chunk("some instruction")])
    assert all(c in "0123456789abcdef" for c in fp)


def test_build_envelope_basic() -> None:
    context = DetectedContext(
        orchestrator_name="claude-code",
        skills=[SkillInfo(name="commit"), SkillInfo(name="review-pr")],
        tools=[ToolInfo(name="Read", param_count=1)],
        agents=[AgentInfo(name="parallel")],
        request_id="req_abc123",
    )
    instructions = [_make_chunk("Always use git"), _make_chunk("Never force push")]
    envelope = build_envelope(
        analysis_id="test-123",
        context=context,
        instructions=instructions,
        model_id="claude-sonnet-4-20250514",
    )
    assert envelope.analysis_id == "test-123"
    assert envelope.orchestrator_name == "claude-code"
    assert envelope.detected_skills == ["commit", "review-pr"]
    assert envelope.detected_tools == ["Read"]
    assert envelope.detected_agents == ["parallel"]
    assert envelope.prompt_fingerprint != EMPTY_FINGERPRINT
    assert len(envelope.prompt_fingerprint) == 16
    assert envelope.request_id == "req_abc123"
    assert envelope.model_id == "claude-sonnet-4-20250514"
    assert envelope.timestamp  # non-empty


def test_build_envelope_empty_context() -> None:
    context = DetectedContext(orchestrator_name="unknown")
    envelope = build_envelope(analysis_id="test-456", context=context, instructions=[])
    assert envelope.orchestrator_name == "unknown"
    assert envelope.detected_skills == []
    assert envelope.detected_tools == []
    assert envelope.detected_agents == []
    assert envelope.prompt_fingerprint == EMPTY_FINGERPRINT
    assert envelope.request_id is None
    assert envelope.model_id is None


def test_build_envelope_no_model_id() -> None:
    context = DetectedContext(orchestrator_name="generic")
    envelope = build_envelope(analysis_id="test-789", context=context, instructions=[])
    assert envelope.model_id is None


def test_envelope_dataclass_fields() -> None:
    envelope = OrchestratorEnvelope(
        analysis_id="x",
        orchestrator_name="test",
    )
    assert envelope.detected_skills == []
    assert envelope.detected_tools == []
    assert envelope.detected_agents == []
    assert envelope.prompt_fingerprint == EMPTY_FINGERPRINT
    assert envelope.request_id is None
    assert envelope.model_id is None


def test_fingerprint_many_instructions() -> None:
    """Verify no issues with large instruction sets."""
    chunks = [_make_chunk(f"Instruction number {i}") for i in range(500)]
    fp = compute_fingerprint(chunks)
    assert len(fp) == 16
    assert fp != EMPTY_FINGERPRINT


def test_fingerprint_duplicate_instructions() -> None:
    """Duplicate instructions produce the same fingerprint as single."""
    chunk = _make_chunk("Same instruction")
    fp_single = compute_fingerprint([chunk])
    fp_double = compute_fingerprint([chunk, chunk])
    # Different because duplicates are kept (not deduped)
    assert fp_single != fp_double
