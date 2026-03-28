"""Tests for the two-phase pipeline runner."""

from __future__ import annotations

import pytest

from promptlint.pipeline import PipelineRunner
from promptlint.pipeline_config import parse_config_dict


@pytest.mark.slow
def test_pipeline_runner_default() -> None:
    config = parse_config_dict({
        "pipelines": {
            "default": {"metrics": ["redundancy", "contradiction", "scorer"]}
        }
    })
    runner = PipelineRunner(config)
    result = runner.run("default", "You must always respond in English. Never use profanity.")

    assert result.instruction_count >= 1
    assert result.severity in ("ok", "warning", "critical")


@pytest.mark.slow
def test_pipeline_runner_scorer_only() -> None:
    config = parse_config_dict({
        "pipelines": {
            "minimal": {"metrics": ["scorer"]}
        }
    })
    runner = PipelineRunner(config)
    result = runner.run("minimal", "You must always respond in English. Never use profanity.")

    assert result.instruction_count >= 1
    # No redundancy or contradiction analysis
    assert result.redundant_groups == []
    assert result.contradictions == []


@pytest.mark.slow
def test_pipeline_runner_with_variant() -> None:
    config = parse_config_dict({
        "stages": {
            "strict-chunker": {
                "base": "chunker",
                "config": {"min_chunk_words": 3},
            }
        },
        "pipelines": {
            "strict": {
                "preprocessing": {"chunker": "strict-chunker"},
                "metrics": ["scorer"],
            }
        },
    })
    runner = PipelineRunner(config)
    result = runner.run("strict", "You must always respond in English. Never use profanity.")

    assert result.instruction_count >= 0


@pytest.mark.slow
def test_pipeline_runner_empty_input() -> None:
    config = parse_config_dict({
        "pipelines": {
            "default": {"metrics": ["scorer"]}
        }
    })
    runner = PipelineRunner(config)
    result = runner.run("default", "")

    assert result.instruction_count == 0


def test_pipeline_runner_unknown_pipeline() -> None:
    config = parse_config_dict({
        "pipelines": {
            "default": {"metrics": ["scorer"]}
        }
    })
    runner = PipelineRunner(config)

    with pytest.raises(ValueError, match="Unknown pipeline 'nonexistent'"):
        runner.run("nonexistent", "hello")


@pytest.mark.slow
def test_pipeline_runner_no_metrics() -> None:
    config = parse_config_dict({
        "pipelines": {
            "empty": {"metrics": []}
        }
    })
    runner = PipelineRunner(config)
    result = runner.run("empty", "You must respond in English.")

    # Should still count instructions from preprocessing
    assert result.instruction_count >= 0
    assert result.redundant_groups == []
    assert result.contradictions == []


@pytest.mark.slow
def test_pipeline_runner_redundancy_only() -> None:
    config = parse_config_dict({
        "pipelines": {
            "redundancy-only": {"metrics": ["redundancy"]}
        }
    })
    runner = PipelineRunner(config)
    result = runner.run(
        "redundancy-only",
        "Always respond in English. You must always reply using English language.",
    )

    # No contradictions since that metric isn't active
    assert result.contradictions == []
