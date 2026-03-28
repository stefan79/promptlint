"""Tests for Stage 5: Contradiction detection."""

import pytest

from promptlint.config import Config
from promptlint.models import ClassifiedChunk


def _make_instruction(text: str, confidence: float = 0.9) -> ClassifiedChunk:
    return ClassifiedChunk(
        text=text,
        source_section="test",
        start_offset=0,
        end_offset=len(text),
        structural_type="bullet",
        label="instruction",
        confidence=confidence,
    )


@pytest.fixture(scope="session")
def pipeline():
    """Load models once for all contradiction tests."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from promptlint.contradiction import ContradictionDetector
    from promptlint.embedder import InstructionEmbedder

    config = Config()
    tokenizer = AutoTokenizer.from_pretrained(config.classifier_model)
    model = AutoModelForSequenceClassification.from_pretrained(config.classifier_model)
    model.eval()

    return {
        "detector": ContradictionDetector(config, model, tokenizer),
        "embedder": InstructionEmbedder(config),
        "config": config,
    }


@pytest.mark.slow
def test_contradiction_detected(pipeline):
    """Contradicting instructions should be detected."""
    instructions = [
        _make_instruction("Be concise and brief in all responses"),
        _make_instruction("Provide comprehensive detailed responses with thorough explanations"),
    ]
    embeddings = pipeline["embedder"].embed(instructions)
    contradictions = pipeline["detector"].detect(instructions, embeddings, [])

    assert len(contradictions) >= 1
    assert contradictions[0].score > 0.5


@pytest.mark.slow
def test_non_contradiction_not_flagged(pipeline):
    """Non-contradicting instructions should not be flagged."""
    instructions = [
        _make_instruction("Always respond in English"),
        _make_instruction("Use markdown formatting for code"),
    ]
    embeddings = pipeline["embedder"].embed(instructions)
    contradictions = pipeline["detector"].detect(instructions, embeddings, [])

    assert len(contradictions) == 0


@pytest.mark.slow
def test_empty_input(pipeline):
    """No instructions returns no contradictions."""
    import numpy as np

    assert pipeline["detector"].detect([], np.empty((0, 384)), []) == []
