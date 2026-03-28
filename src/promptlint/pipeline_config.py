"""YAML configuration parsing for pipeline DSL (spec 02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class StageVariant:
    """A named variant of a built-in stage with config overrides."""

    name: str
    base: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineDefinition:
    """A named pipeline: optional preprocessing overrides + metric stage list."""

    name: str
    metrics: list[str] = field(default_factory=list)
    preprocessing: dict[str, str] = field(default_factory=dict)


@dataclass
class BenchmarkDefinition:
    """A named benchmark run configuration."""

    name: str
    pipelines: list[str] = field(default_factory=list)
    corpus: str = ""
    metrics: list[str] = field(default_factory=list)
    repeat: int = 5


@dataclass
class PipelineConfig:
    """Parsed pipeline DSL configuration."""

    stages: dict[str, StageVariant] = field(default_factory=dict)
    pipelines: dict[str, PipelineDefinition] = field(default_factory=dict)
    benchmarks: dict[str, BenchmarkDefinition] = field(default_factory=dict)


BUILT_IN_PREPROCESSING = ["chunker", "classifier", "embedder"]
BUILT_IN_METRICS = ["redundancy", "contradiction", "scorer"]
BUILT_IN_STAGES = BUILT_IN_PREPROCESSING + BUILT_IN_METRICS


def load_config(path: str | Path) -> PipelineConfig:
    """Load and validate a pipeline DSL YAML file."""
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        msg = f"Expected YAML mapping, got {type(raw).__name__}"
        raise ValueError(msg)
    return _parse_config(raw)


def parse_config_dict(raw: dict[str, Any]) -> PipelineConfig:
    """Parse a pipeline config from an already-loaded dict."""
    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> PipelineConfig:
    config = PipelineConfig()

    # Parse stage variants
    for name, defn in raw.get("stages", {}).items():
        if not isinstance(defn, dict):
            msg = f"Stage '{name}' must be a mapping"
            raise ValueError(msg)
        base = defn.get("base")
        if not base:
            msg = f"Stage '{name}' must have a 'base' field"
            raise ValueError(msg)
        if base not in BUILT_IN_STAGES:
            msg = f"Stage '{name}' has unknown base '{base}'. Must be one of: {BUILT_IN_STAGES}"
            raise ValueError(msg)
        config.stages[name] = StageVariant(
            name=name,
            base=base,
            config=defn.get("config", {}),
        )

    # Parse pipelines
    for name, defn in raw.get("pipelines", {}).items():
        if not isinstance(defn, dict):
            msg = f"Pipeline '{name}' must be a mapping"
            raise ValueError(msg)
        metrics = defn.get("metrics", [])
        preprocessing = defn.get("preprocessing", {})

        # Validate metrics reference built-in metric stages or stage variants
        for m in metrics:
            _resolve_stage(m, "metric", config.stages)

        # Validate preprocessing overrides reference preprocessing stages
        for slot, variant_name in preprocessing.items():
            if slot not in BUILT_IN_PREPROCESSING:
                msg = f"Pipeline '{name}': preprocessing slot '{slot}' must be one of {BUILT_IN_PREPROCESSING}"
                raise ValueError(msg)
            resolved_base = _resolve_stage(variant_name, "preprocessing", config.stages)
            if resolved_base != slot:
                msg = (
                    f"Pipeline '{name}': preprocessing override '{variant_name}' "
                    f"has base '{resolved_base}', expected '{slot}'"
                )
                raise ValueError(msg)

        config.pipelines[name] = PipelineDefinition(
            name=name,
            metrics=metrics,
            preprocessing=preprocessing,
        )

    # Parse benchmarks
    for name, defn in raw.get("benchmarks", {}).items():
        if not isinstance(defn, dict):
            msg = f"Benchmark '{name}' must be a mapping"
            raise ValueError(msg)
        pipeline_names = defn.get("pipelines", [])
        for pname in pipeline_names:
            if pname not in config.pipelines:
                msg = f"Benchmark '{name}' references unknown pipeline '{pname}'"
                raise ValueError(msg)
        config.benchmarks[name] = BenchmarkDefinition(
            name=name,
            pipelines=pipeline_names,
            corpus=defn.get("corpus", ""),
            metrics=defn.get("metrics", []),
            repeat=defn.get("repeat", 5),
        )

    return config


def _resolve_stage(name: str, kind: str, variants: dict[str, StageVariant]) -> str:
    """Resolve a stage name to its built-in base. Returns the base name."""
    if name in BUILT_IN_STAGES:
        return name
    if name in variants:
        return variants[name].base
    msg = f"Unknown {kind} stage '{name}'. Must be a built-in stage or defined variant."
    raise ValueError(msg)
