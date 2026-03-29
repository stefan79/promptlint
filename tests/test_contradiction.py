"""Tests for Stage 5: Contradiction detection."""

import pytest

from promptlint.config import Config


@pytest.fixture(scope="session")
def pipeline():
    """Load models once for all contradiction tests."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from promptlint.contradiction import ContradictionDetector
    from promptlint.embedder import InstructionEmbedder

    config = Config()
    tokenizer = AutoTokenizer.from_pretrained(config.contradiction_model)
    model = AutoModelForSequenceClassification.from_pretrained(config.contradiction_model)
    model.eval()

    return {
        "detector": ContradictionDetector(config, model, tokenizer),
        "embedder": InstructionEmbedder(config),
        "config": config,
    }


@pytest.mark.slow
def test_contradiction_detected(pipeline, make_instruction):
    """Contradicting instructions should be detected."""
    instructions = [
        make_instruction("Be concise and brief in all responses"),
        make_instruction("Provide comprehensive detailed responses with thorough explanations"),
    ]
    embeddings = pipeline["embedder"].embed(instructions)
    contradictions = pipeline["detector"].detect(instructions, embeddings, [])

    assert len(contradictions) >= 1
    assert contradictions[0].score > 0.5


@pytest.mark.slow
def test_non_contradiction_not_flagged(pipeline, make_instruction):
    """Non-contradicting instructions should not be flagged."""
    instructions = [
        make_instruction("Always respond in English"),
        make_instruction("Use markdown formatting for code"),
    ]
    embeddings = pipeline["embedder"].embed(instructions)
    contradictions = pipeline["detector"].detect(instructions, embeddings, [])

    assert len(contradictions) == 0


@pytest.mark.slow
def test_empty_input(pipeline):
    """No instructions returns no contradictions."""
    import numpy as np

    assert pipeline["detector"].detect([], np.empty((0, 384)), []) == []
