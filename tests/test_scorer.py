"""Tests for Stage 6: Scorer."""

from promptlint.config import Config
from promptlint.models import ClassifiedChunk, Contradiction, RedundancyGroup
from promptlint.scorer import score


def _make_non_instruction(text: str) -> ClassifiedChunk:
    return ClassifiedChunk(
        text=text,
        source_section="test",
        start_offset=0,
        end_offset=len(text),
        structural_type="paragraph",
        label="non_instruction",
        confidence=0.8,
    )


def test_severity_ok(make_instruction):
    """Few instructions, no contradictions → ok."""
    config = Config()
    instructions = [make_instruction(f"Rule {i}") for i in range(10)]
    result = score(instructions, [], [], [], instructions, "x " * 500, config)
    assert result.severity == "ok"
    assert result.instruction_count == 10


def test_severity_warning(make_instruction):
    """Instruction count in warning range."""
    config = Config(warn_instructions=5, critical_instructions=20)
    instructions = [make_instruction(f"Rule {i}") for i in range(10)]
    result = score(instructions, [], [], [], instructions, "x " * 5000, config)
    assert result.severity == "warning"


def test_severity_critical_instructions(make_instruction):
    """Instruction count above critical threshold."""
    config = Config(critical_instructions=5)
    instructions = [make_instruction(f"Rule {i}") for i in range(10)]
    result = score(instructions, [], [], [], instructions, "x " * 5000, config)
    assert result.severity == "critical"


def test_severity_critical_contradictions(make_instruction):
    """Many contradictions → critical."""
    config = Config(critical_contradictions=2)
    inst_a = make_instruction("Be concise")
    inst_b = make_instruction("Be verbose")
    inst_c = make_instruction("Use English")
    inst_d = make_instruction("Use French")
    inst_e = make_instruction("No bullets")
    inst_f = make_instruction("Use bullets")
    instructions = [inst_a, inst_b, inst_c, inst_d, inst_e, inst_f]
    contradictions = [
        Contradiction(instruction_a=inst_a, instruction_b=inst_b, score=0.9, direction="bidirectional"),
        Contradiction(instruction_a=inst_c, instruction_b=inst_d, score=0.85, direction="bidirectional"),
        Contradiction(instruction_a=inst_e, instruction_b=inst_f, score=0.8, direction="bidirectional"),
    ]
    result = score(instructions, [], [], contradictions, instructions, "x " * 5000, config)
    assert result.severity == "critical"


def test_redundancy_ratio(make_instruction):
    """Redundancy ratio is computed correctly."""
    config = Config()
    instructions = [make_instruction(f"Rule {i}") for i in range(10)]
    canon = instructions[0]
    dups = [instructions[1], instructions[2]]
    groups = [RedundancyGroup(canonical=canon, duplicates=dups, similarity=0.9)]
    result = score(instructions, [], groups, [], instructions, "x " * 5000, config)
    assert result.unique_instruction_count == 8  # 10 - 2 duplicates
    assert abs(result.redundancy_ratio - 0.2) < 0.01


def test_section_distribution(make_instruction):
    """Instructions are counted per section."""
    config = Config()
    instructions = [
        make_instruction("Rule A", section="system"),
        make_instruction("Rule B", section="system"),
        make_instruction("Rule C", section="skills"),
    ]
    result = score(instructions, [], [], [], instructions, "x " * 500, config)
    assert result.section_distribution["system"] == 2
    assert result.section_distribution["skills"] == 1


def test_density_calculation(make_instruction):
    """Density is instructions per 1K tokens."""
    config = Config()
    instructions = [make_instruction("Be concise")]
    # "word " repeated 500 times ≈ 500 tokens
    text = "word " * 500
    result = score(instructions, [], [], [], instructions, text, config)
    assert result.density > 0
