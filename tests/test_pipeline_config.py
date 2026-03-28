"""Tests for pipeline DSL YAML parsing."""

from __future__ import annotations

import pytest

from promptlint.pipeline_config import (
    load_config,
    parse_config_dict,
)


def test_parse_empty_config() -> None:
    config = parse_config_dict({})
    assert config.stages == {}
    assert config.pipelines == {}
    assert config.benchmarks == {}


def test_parse_stage_variant() -> None:
    raw = {
        "stages": {
            "chunker-strict": {
                "base": "chunker",
                "config": {"min_chunk_words": 3},
            }
        }
    }
    config = parse_config_dict(raw)
    assert "chunker-strict" in config.stages
    variant = config.stages["chunker-strict"]
    assert variant.base == "chunker"
    assert variant.config == {"min_chunk_words": 3}


def test_parse_stage_variant_missing_base() -> None:
    raw = {"stages": {"bad": {"config": {}}}}
    with pytest.raises(ValueError, match="must have a 'base' field"):
        parse_config_dict(raw)


def test_parse_stage_variant_unknown_base() -> None:
    raw = {"stages": {"bad": {"base": "nonexistent"}}}
    with pytest.raises(ValueError, match="unknown base 'nonexistent'"):
        parse_config_dict(raw)


def test_parse_pipeline_default_metrics() -> None:
    raw = {
        "pipelines": {
            "default": {"metrics": ["redundancy", "contradiction", "scorer"]}
        }
    }
    config = parse_config_dict(raw)
    assert "default" in config.pipelines
    assert config.pipelines["default"].metrics == ["redundancy", "contradiction", "scorer"]


def test_parse_pipeline_with_preprocessing_override() -> None:
    raw = {
        "stages": {
            "chunker-strict": {"base": "chunker", "config": {"min_chunk_words": 3}}
        },
        "pipelines": {
            "strict": {
                "preprocessing": {"chunker": "chunker-strict"},
                "metrics": ["scorer"],
            }
        },
    }
    config = parse_config_dict(raw)
    assert config.pipelines["strict"].preprocessing == {"chunker": "chunker-strict"}


def test_parse_pipeline_preprocessing_wrong_slot() -> None:
    raw = {
        "stages": {
            "chunker-strict": {"base": "chunker", "config": {}}
        },
        "pipelines": {
            "bad": {
                "preprocessing": {"classifier": "chunker-strict"},
                "metrics": ["scorer"],
            }
        },
    }
    with pytest.raises(ValueError, match="has base 'chunker', expected 'classifier'"):
        parse_config_dict(raw)


def test_parse_pipeline_unknown_metric() -> None:
    raw = {
        "pipelines": {
            "bad": {"metrics": ["nonexistent"]}
        }
    }
    with pytest.raises(ValueError, match="Unknown metric stage 'nonexistent'"):
        parse_config_dict(raw)


def test_parse_pipeline_with_variant_metric() -> None:
    raw = {
        "stages": {
            "skip-contradiction-short": {
                "base": "contradiction",
                "config": {"min_instructions": 10},
            }
        },
        "pipelines": {
            "smart": {"metrics": ["redundancy", "skip-contradiction-short", "scorer"]}
        },
    }
    config = parse_config_dict(raw)
    assert "skip-contradiction-short" in config.pipelines["smart"].metrics


def test_parse_benchmark() -> None:
    raw = {
        "pipelines": {
            "default": {"metrics": ["scorer"]},
            "fast": {"metrics": ["scorer"]},
        },
        "benchmarks": {
            "compare": {
                "pipelines": ["default", "fast"],
                "corpus": "./fixtures/",
                "metrics": ["latency_p50", "instruction_count"],
                "repeat": 3,
            }
        },
    }
    config = parse_config_dict(raw)
    bench = config.benchmarks["compare"]
    assert bench.pipelines == ["default", "fast"]
    assert bench.corpus == "./fixtures/"
    assert bench.repeat == 3


def test_parse_benchmark_unknown_pipeline() -> None:
    raw = {
        "pipelines": {"default": {"metrics": ["scorer"]}},
        "benchmarks": {"bad": {"pipelines": ["nonexistent"]}},
    }
    with pytest.raises(ValueError, match="unknown pipeline 'nonexistent'"):
        parse_config_dict(raw)


def test_parse_pipeline_invalid_preprocessing_slot() -> None:
    raw = {
        "stages": {"my-variant": {"base": "chunker", "config": {}}},
        "pipelines": {
            "bad": {
                "preprocessing": {"nonexistent": "my-variant"},
                "metrics": ["scorer"],
            }
        },
    }
    with pytest.raises(ValueError, match="preprocessing slot 'nonexistent'"):
        parse_config_dict(raw)


def test_full_config() -> None:
    raw = {
        "stages": {
            "chunker-strict": {"base": "chunker", "config": {"min_chunk_words": 3}},
            "fast-classifier": {"base": "classifier", "config": {"classification_threshold": 0.70}},
        },
        "pipelines": {
            "default": {"metrics": ["redundancy", "contradiction", "scorer"]},
            "strict": {
                "preprocessing": {"chunker": "chunker-strict"},
                "metrics": ["redundancy", "contradiction", "scorer"],
            },
            "fast": {
                "preprocessing": {"classifier": "fast-classifier"},
                "metrics": ["redundancy", "scorer"],
            },
        },
        "benchmarks": {
            "compare": {
                "pipelines": ["default", "strict", "fast"],
                "corpus": "./fixtures/",
                "repeat": 5,
            }
        },
    }
    config = parse_config_dict(raw)
    assert len(config.stages) == 2
    assert len(config.pipelines) == 3
    assert len(config.benchmarks) == 1


def test_load_config_from_file(tmp_path: object) -> None:
    import pathlib

    p = pathlib.Path(str(tmp_path)) / "test.yaml"
    p.write_text(
        "pipelines:\n"
        "  default:\n"
        "    metrics: [scorer]\n"
    )
    config = load_config(p)
    assert "default" in config.pipelines


def test_stage_variant_no_config() -> None:
    raw = {
        "stages": {
            "chunker-v2": {"base": "chunker"}
        }
    }
    config = parse_config_dict(raw)
    assert config.stages["chunker-v2"].config == {}
