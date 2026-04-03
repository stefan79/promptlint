"""Unified configuration loading for promptlint (spec 06).

Discovers, parses, validates, and resolves a single promptlint.yaml into typed
dataclasses that wire together pipelines, backends, gateways, and orchestrators.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from promptlint.pipeline_config import (
    BenchmarkDefinition,
    PipelineConfig,
    PipelineDefinition,
    StageVariant,
    parse_config_dict,
)

# ---------------------------------------------------------------------------
# Config file discovery chain
# ---------------------------------------------------------------------------

_SEARCH_CHAIN: list[Path] = [
    Path("promptlint.yaml"),
    Path.home() / ".config" / "promptlint" / "promptlint.yaml",
    Path("/etc/promptlint/promptlint.yaml"),
]

SUPPORTED_VERSIONS: set[int] = {1}


def discover_config(explicit_path: str | None = None) -> Path | None:
    """Return the first config file found in the search chain, or None."""
    if explicit_path is not None:
        p = Path(explicit_path)
        if not p.exists():
            msg = f"Config file not found: {explicit_path}"
            raise FileNotFoundError(msg)
        return p
    for candidate in _SEARCH_CHAIN:
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Env var interpolation
# ---------------------------------------------------------------------------

_ENV_RE = re.compile(r"\$\{(\w+)\}")


def resolve_env_vars(value: object) -> object:
    """Recursively replace ${VAR} references with environment variable values."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Settings dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GatewaySettings:
    """Gateway listener configuration."""

    type: str = "builtin-proxy"
    listen: str = "0.0.0.0:8100"
    pipeline: str = ""
    backends: list[str] = field(default_factory=list)
    block_on: str | None = None
    target: str = "https://api.anthropic.com"
    vendor_override: str | None = None
    max_concurrent: int = 10
    timeout: float = 300.0


@dataclass
class FeedbackSettings:
    enabled: bool = False
    backend: str = ""


@dataclass
class DatasetSettings:
    enabled: bool = False
    path: str = ""
    include_user_messages: bool = False


@dataclass
class OrchestratorSettings:
    """Orchestrator adapter configuration."""

    type: str = "generic"
    skill_detection: bool = True
    prompt_fingerprint: bool = True
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings)
    dataset: DatasetSettings = field(default_factory=DatasetSettings)


@dataclass
class AnalysisSettings:
    """Analysis threshold overrides — maps to Config fields."""

    classification_threshold: float | None = None
    contradiction_threshold: float | None = None
    redundancy_similarity: float | None = None
    warn_instructions: int | None = None
    critical_instructions: int | None = None
    warn_density: float | None = None
    critical_density: float | None = None


@dataclass
class PromptLintSettings:
    """Top-level parsed configuration from promptlint.yaml."""

    version: int = 1

    # Pipeline DSL sections (delegated to pipeline_config.py)
    pipeline_config: PipelineConfig = field(default_factory=PipelineConfig)

    # Backend definitions: name -> emitter config dict
    backends: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Gateway
    gateway: GatewaySettings = field(default_factory=GatewaySettings)

    # Orchestrator
    orchestrator: OrchestratorSettings = field(default_factory=OrchestratorSettings)

    # Global analysis thresholds
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)

    @property
    def stages(self) -> dict[str, StageVariant]:
        return self.pipeline_config.stages

    @property
    def pipelines(self) -> dict[str, PipelineDefinition]:
        return self.pipeline_config.pipelines

    @property
    def benchmarks(self) -> dict[str, BenchmarkDefinition]:
        return self.pipeline_config.benchmarks


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when the config file is invalid."""


def _validate_version(raw: dict[str, Any]) -> int:
    version = raw.get("version", 1)
    if not isinstance(version, int):
        msg = f"'version' must be an integer, got {type(version).__name__}"
        raise ConfigError(msg)
    if version not in SUPPORTED_VERSIONS:
        msg = f"Unsupported config version {version}. Supported: {sorted(SUPPORTED_VERSIONS)}"
        raise ConfigError(msg)
    return version


def _validate_backends(backends: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate backends section and return name -> config dict."""
    result: dict[str, dict[str, Any]] = {}
    for name, config in backends.items():
        if not isinstance(config, dict):
            msg = f"Backend '{name}' must be a mapping, got {type(config).__name__}"
            raise ConfigError(msg)
        if "type" not in config:
            msg = f"Backend '{name}' must have a 'type' field"
            raise ConfigError(msg)
        result[name] = config
    return result


def _parse_gateway(raw: dict[str, Any]) -> GatewaySettings:
    if not isinstance(raw, dict):
        msg = f"'gateway' must be a mapping, got {type(raw).__name__}"
        raise ConfigError(msg)
    gw_type = raw.get("type", "builtin-proxy")
    valid_types = {"builtin-proxy", "sdk-middleware"}
    if gw_type not in valid_types:
        msg = f"Unknown gateway type '{gw_type}'. Supported: {sorted(valid_types)}"
        raise ConfigError(msg)
    return GatewaySettings(
        type=gw_type,
        listen=raw.get("listen", "0.0.0.0:8100"),
        pipeline=raw.get("pipeline", ""),
        backends=raw.get("backends", []),
        block_on=raw.get("block_on"),
        target=raw.get("target", "https://api.anthropic.com"),
        vendor_override=raw.get("vendor_override"),
        max_concurrent=raw.get("max_concurrent", 10),
        timeout=raw.get("timeout", 300.0),
    )


def _parse_orchestrator(raw: dict[str, Any]) -> OrchestratorSettings:
    if not isinstance(raw, dict):
        msg = f"'orchestrator' must be a mapping, got {type(raw).__name__}"
        raise ConfigError(msg)
    feedback_raw = raw.get("feedback", {})
    if feedback_raw and not isinstance(feedback_raw, dict):
        msg = f"'orchestrator.feedback' must be a mapping, got {type(feedback_raw).__name__}"
        raise ConfigError(msg)
    dataset_raw = raw.get("dataset", {})
    if dataset_raw and not isinstance(dataset_raw, dict):
        msg = f"'orchestrator.dataset' must be a mapping, got {type(dataset_raw).__name__}"
        raise ConfigError(msg)
    feedback = feedback_raw if isinstance(feedback_raw, dict) else {}
    dataset = dataset_raw if isinstance(dataset_raw, dict) else {}
    return OrchestratorSettings(
        type=raw.get("type", "generic"),
        skill_detection=raw.get("skill_detection", True),
        prompt_fingerprint=raw.get("prompt_fingerprint", True),
        feedback=FeedbackSettings(
            enabled=feedback.get("enabled", False),
            backend=feedback.get("backend", ""),
        ),
        dataset=DatasetSettings(
            enabled=dataset.get("enabled", False),
            path=dataset.get("path", ""),
            include_user_messages=dataset.get("include_user_messages", False),
        ),
    )


def _parse_analysis(raw: dict[str, Any]) -> AnalysisSettings:
    if not isinstance(raw, dict):
        msg = f"'analysis' must be a mapping, got {type(raw).__name__}"
        raise ConfigError(msg)
    return AnalysisSettings(
        classification_threshold=raw.get("classification_threshold"),
        contradiction_threshold=raw.get("contradiction_threshold"),
        redundancy_similarity=raw.get("redundancy_similarity"),
        warn_instructions=raw.get("warn_instructions"),
        critical_instructions=raw.get("critical_instructions"),
        warn_density=raw.get("warn_density"),
        critical_density=raw.get("critical_density"),
    )


def _validate_gateway_backend_refs(settings: PromptLintSettings) -> None:
    """Check that gateway.backends all reference defined backends."""
    for ref in settings.gateway.backends:
        if ref not in settings.backends:
            msg = f"Gateway references unknown backend '{ref}'. Defined backends: {sorted(settings.backends)}"
            raise ConfigError(msg)


def _validate_gateway_pipeline_ref(settings: PromptLintSettings) -> None:
    """Check that gateway.pipeline references a defined pipeline."""
    if settings.gateway.pipeline and settings.gateway.pipeline not in settings.pipelines:
        msg = (
            f"Gateway references unknown pipeline '{settings.gateway.pipeline}'. "
            f"Defined pipelines: {sorted(settings.pipelines)}"
        )
        raise ConfigError(msg)


def _validate_feedback_backend_ref(settings: PromptLintSettings) -> None:
    """Check that orchestrator.feedback.backend references a defined backend."""
    fb = settings.orchestrator.feedback
    if fb.enabled and fb.backend and fb.backend not in settings.backends:
        msg = (
            f"Orchestrator feedback references unknown backend '{fb.backend}'. "
            f"Defined backends: {sorted(settings.backends)}"
        )
        raise ConfigError(msg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_settings(path: str | Path) -> PromptLintSettings:
    """Load and validate a promptlint.yaml config file."""
    raw_text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text)
    if raw is None:
        return PromptLintSettings()
    if not isinstance(raw, dict):
        msg = f"Config file must be a YAML mapping, got {type(raw).__name__}"
        raise ConfigError(msg)
    return parse_settings_dict(raw)


def parse_settings_dict(raw: dict[str, Any]) -> PromptLintSettings:
    """Parse a PromptLintSettings from an already-loaded dict."""
    # Resolve env vars throughout
    resolved: dict[str, Any] = {}
    for k, v in raw.items():
        resolved[k] = resolve_env_vars(v)

    version = _validate_version(resolved)

    # Delegate pipeline DSL sections (stages, pipelines, benchmarks) to existing parser
    pipeline_sections: dict[str, Any] = {}
    for key in ("stages", "pipelines", "benchmarks"):
        if key in resolved:
            pipeline_sections[key] = resolved[key]
    pipeline_config = parse_config_dict(pipeline_sections) if pipeline_sections else PipelineConfig()

    # Backends
    backends_raw = resolved.get("backends", {})
    if backends_raw and not isinstance(backends_raw, dict):
        msg = f"'backends' must be a mapping, got {type(backends_raw).__name__}"
        raise ConfigError(msg)
    backends = _validate_backends(backends_raw) if backends_raw else {}

    # Gateway
    gateway = _parse_gateway(resolved["gateway"]) if "gateway" in resolved else GatewaySettings()

    # Orchestrator
    orchestrator = (
        _parse_orchestrator(resolved["orchestrator"]) if "orchestrator" in resolved else OrchestratorSettings()
    )

    # Analysis thresholds
    analysis = _parse_analysis(resolved["analysis"]) if "analysis" in resolved else AnalysisSettings()

    settings = PromptLintSettings(
        version=version,
        pipeline_config=pipeline_config,
        backends=backends,
        gateway=gateway,
        orchestrator=orchestrator,
        analysis=analysis,
    )

    # Cross-reference validation
    _validate_gateway_backend_refs(settings)
    _validate_gateway_pipeline_ref(settings)
    _validate_feedback_backend_ref(settings)

    return settings


def validate_config(path: str | Path, deep: bool = False) -> list[str]:
    """Validate a config file. Returns list of error strings (empty = valid).

    When deep=True, also checks that backends are reachable (connectivity test).
    """
    errors: list[str] = []
    try:
        settings = load_settings(path)
    except (ConfigError, FileNotFoundError, yaml.YAMLError) as e:
        errors.append(str(e))
        return errors
    except Exception as e:
        errors.append(f"Unexpected error: {e}")
        return errors

    if deep:
        errors.extend(_deep_validate_backends(settings))

    return errors


def _deep_validate_backends(settings: PromptLintSettings) -> list[str]:
    """Test connectivity to each configured backend."""
    from promptlint.emitters import create_emitter
    from promptlint.models import AnalysisResult, Feedback

    errors: list[str] = []
    test_result = AnalysisResult()
    test_feedback = Feedback(analysis_id="validate-test", rating="good", note="config validation")

    for name, config in settings.backends.items():
        try:
            emitter = create_emitter(config)
            emitter.write_analysis(test_result)
            emitter.write_feedback(test_feedback)
            if hasattr(emitter, "close"):
                emitter.close()
        except Exception as e:
            errors.append(f"Backend '{name}' ({config.get('type', '?')}): {e}")

    return errors


def settings_to_config(settings: PromptLintSettings) -> dict[str, Any]:
    """Convert AnalysisSettings overrides into kwargs for Config()."""
    return {
        f.name: getattr(settings.analysis, f.name)
        for f in fields(settings.analysis)
        if getattr(settings.analysis, f.name) is not None
    }
