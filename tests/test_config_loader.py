"""Tests for config_loader.py (spec 06 — Configuration Language)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from promptlint.config_loader import (
    ConfigError,
    PromptLintSettings,
    discover_config,
    load_settings,
    parse_settings_dict,
    settings_to_config,
    validate_config,
)

# ---------------------------------------------------------------------------
# discover_config
# ---------------------------------------------------------------------------


def test_discover_explicit_path(tmp_path: Path) -> None:
    cfg = tmp_path / "my.yaml"
    cfg.write_text("version: 1\n")
    assert discover_config(str(cfg)) == cfg


def test_discover_explicit_path_missing() -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        discover_config("/nonexistent/promptlint.yaml")


def test_discover_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("version: 1\n")
    assert discover_config() == Path("promptlint.yaml")


def test_discover_home_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    home_cfg = tmp_path / ".config" / "promptlint" / "promptlint.yaml"
    home_cfg.parent.mkdir(parents=True)
    home_cfg.write_text("version: 1\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    # Patch the search chain to use the tmp_path home
    import promptlint.config_loader as cl

    monkeypatch.setattr(
        cl,
        "_SEARCH_CHAIN",
        [
            Path("promptlint.yaml"),
            tmp_path / ".config" / "promptlint" / "promptlint.yaml",
            Path("/etc/promptlint/promptlint.yaml"),
        ],
    )
    found = discover_config()
    assert found is not None
    assert "promptlint.yaml" in str(found)


def test_discover_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert discover_config() is None


# ---------------------------------------------------------------------------
# load_settings — happy path
# ---------------------------------------------------------------------------


def test_load_minimal(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("version: 1\n")
    settings = load_settings(cfg)
    assert settings.version == 1
    assert settings.backends == {}
    assert settings.gateway.type == "builtin-proxy"
    assert settings.orchestrator.type == "generic"


def test_load_empty_file(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("")
    settings = load_settings(cfg)
    assert settings.version == 1


def test_load_full_config(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1

        backends:
          local:
            type: jsonl
            path: /tmp/results.jsonl
          search:
            type: elasticsearch
            url: https://es.internal:9200
            index: promptlint

        gateway:
          type: builtin-proxy
          listen: 0.0.0.0:8100
          pipeline: ""
          backends: [local, search]
          block_on: critical
          target: https://api.anthropic.com

        orchestrator:
          type: claude-code
          skill_detection: true
          prompt_fingerprint: true
          feedback:
            enabled: true
            backend: local
          dataset:
            enabled: false
            path: ""

        analysis:
          classification_threshold: 0.60
          warn_instructions: 100
    """)
    )
    settings = load_settings(cfg)
    assert settings.version == 1
    assert "local" in settings.backends
    assert "search" in settings.backends
    assert settings.backends["local"]["type"] == "jsonl"
    assert settings.gateway.type == "builtin-proxy"
    assert settings.gateway.block_on == "critical"
    assert settings.gateway.backends == ["local", "search"]
    assert settings.orchestrator.type == "claude-code"
    assert settings.orchestrator.feedback.enabled is True
    assert settings.orchestrator.feedback.backend == "local"
    assert settings.analysis.classification_threshold == 0.60
    assert settings.analysis.warn_instructions == 100


# ---------------------------------------------------------------------------
# load_settings — with pipelines (delegates to pipeline_config)
# ---------------------------------------------------------------------------


def test_load_with_pipelines(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1

        pipelines:
          fast:
            metrics: [scorer]

        backends:
          local:
            type: jsonl
            path: /tmp/out.jsonl

        gateway:
          type: builtin-proxy
          pipeline: fast
          backends: [local]
    """)
    )
    settings = load_settings(cfg)
    assert "fast" in settings.pipelines
    assert settings.pipelines["fast"].metrics == ["scorer"]


# ---------------------------------------------------------------------------
# Env var interpolation
# ---------------------------------------------------------------------------


def test_env_var_interpolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_ES_URL", "https://es.prod:9200")
    monkeypatch.setenv("MY_ES_KEY", "secret123")
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        backends:
          search:
            type: elasticsearch
            url: ${MY_ES_URL}
            auth: ${MY_ES_KEY}
            index: promptlint
    """)
    )
    settings = load_settings(cfg)
    assert settings.backends["search"]["url"] == "https://es.prod:9200"
    assert settings.backends["search"]["auth"] == "secret123"


def test_env_var_missing_kept_as_is(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        backends:
          search:
            type: elasticsearch
            url: ${NONEXISTENT_VAR}
            index: promptlint
    """)
    )
    settings = load_settings(cfg)
    assert settings.backends["search"]["url"] == "${NONEXISTENT_VAR}"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_invalid_version(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("version: 99\n")
    with pytest.raises(ConfigError, match="Unsupported config version 99"):
        load_settings(cfg)


def test_version_not_int(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text('version: "one"\n')
    with pytest.raises(ConfigError, match="must be an integer"):
        load_settings(cfg)


def test_invalid_yaml(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("version: 1\nbackends: [not a mapping")
    with pytest.raises(yaml.YAMLError):
        load_settings(cfg)


def test_not_a_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("- item1\n- item2\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_settings(cfg)


def test_backends_section_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        backends:
          - jsonl
          - sqlite
    """)
    )
    with pytest.raises(ConfigError, match="'backends' must be a mapping"):
        load_settings(cfg)


def test_orchestrator_feedback_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        orchestrator:
          type: claude-code
          feedback: true
    """)
    )
    with pytest.raises(ConfigError, match=r"'orchestrator\.feedback' must be a mapping"):
        load_settings(cfg)


def test_orchestrator_dataset_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        orchestrator:
          type: claude-code
          dataset: "/some/path"
    """)
    )
    with pytest.raises(ConfigError, match=r"'orchestrator\.dataset' must be a mapping"):
        load_settings(cfg)


def test_backend_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        backends:
          bad: "just a string"
    """)
    )
    with pytest.raises(ConfigError, match="Backend 'bad' must be a mapping"):
        load_settings(cfg)


def test_backend_missing_type(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        backends:
          bad:
            path: /tmp/out.jsonl
    """)
    )
    with pytest.raises(ConfigError, match="must have a 'type' field"):
        load_settings(cfg)


def test_unknown_gateway_type(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        gateway:
          type: nginx-sidecar
    """)
    )
    with pytest.raises(ConfigError, match="Unknown gateway type"):
        load_settings(cfg)


def test_gateway_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        gateway: "just a string"
    """)
    )
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_settings(cfg)


def test_gateway_unknown_backend_ref(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        gateway:
          type: builtin-proxy
          backends: [nonexistent]
    """)
    )
    with pytest.raises(ConfigError, match="unknown backend 'nonexistent'"):
        load_settings(cfg)


def test_gateway_unknown_pipeline_ref(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        gateway:
          type: builtin-proxy
          pipeline: nonexistent
    """)
    )
    with pytest.raises(ConfigError, match="unknown pipeline 'nonexistent'"):
        load_settings(cfg)


def test_feedback_unknown_backend_ref(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        orchestrator:
          type: generic
          feedback:
            enabled: true
            backend: nonexistent
    """)
    )
    with pytest.raises(ConfigError, match="unknown backend 'nonexistent'"):
        load_settings(cfg)


def test_orchestrator_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        orchestrator: "just a string"
    """)
    )
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_settings(cfg)


def test_analysis_not_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        analysis: 42
    """)
    )
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_settings(cfg)


# ---------------------------------------------------------------------------
# parse_settings_dict
# ---------------------------------------------------------------------------


def test_parse_settings_dict_empty() -> None:
    settings = parse_settings_dict({})
    assert settings.version == 1
    assert settings.backends == {}


def test_parse_settings_dict_with_backends() -> None:
    settings = parse_settings_dict(
        {
            "backends": {
                "local": {"type": "jsonl", "path": "/tmp/out.jsonl"},
            },
        }
    )
    assert "local" in settings.backends


# ---------------------------------------------------------------------------
# settings_to_config
# ---------------------------------------------------------------------------


def test_settings_to_config_empty() -> None:
    settings = PromptLintSettings()
    overrides = settings_to_config(settings)
    assert overrides == {}


def test_settings_to_config_with_overrides() -> None:
    settings = PromptLintSettings()
    settings.analysis.classification_threshold = 0.55
    settings.analysis.warn_instructions = 100
    overrides = settings_to_config(settings)
    assert overrides == {
        "classification_threshold": 0.55,
        "warn_instructions": 100,
    }


def test_settings_to_config_all_fields() -> None:
    settings = PromptLintSettings()
    settings.analysis.classification_threshold = 0.5
    settings.analysis.contradiction_threshold = 0.6
    settings.analysis.redundancy_similarity = 0.7
    settings.analysis.warn_instructions = 80
    settings.analysis.critical_instructions = 150
    settings.analysis.warn_density = 60.0
    settings.analysis.critical_density = 90.0
    overrides = settings_to_config(settings)
    assert len(overrides) == 7


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def test_validate_config_valid(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("version: 1\n")
    errors = validate_config(cfg)
    assert errors == []


def test_validate_config_invalid(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text("version: 99\n")
    errors = validate_config(cfg)
    assert len(errors) == 1
    assert "Unsupported" in errors[0]


def test_validate_config_file_not_found() -> None:
    errors = validate_config("/nonexistent.yaml")
    assert len(errors) == 1
    assert "No such file" in errors[0] or "not found" in errors[0].lower()


def test_validate_config_deep_with_valid_backend(tmp_path: Path) -> None:
    out_file = tmp_path / "results.jsonl"
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent(f"""\
        version: 1
        backends:
          local:
            type: jsonl
            path: {out_file}
    """)
    )
    errors = validate_config(cfg, deep=True)
    assert errors == []


def test_validate_config_deep_with_bad_backend(tmp_path: Path) -> None:
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        backends:
          bad_es:
            type: elasticsearch
            url: http://localhost:1
            index: test
    """)
    )
    errors = validate_config(cfg, deep=True)
    assert len(errors) >= 1
    assert "bad_es" in errors[0]


# ---------------------------------------------------------------------------
# Gateway settings defaults
# ---------------------------------------------------------------------------


def test_gateway_defaults() -> None:
    settings = parse_settings_dict({"gateway": {"type": "builtin-proxy"}})
    gw = settings.gateway
    assert gw.listen == "0.0.0.0:8100"
    assert gw.target == "https://api.anthropic.com"
    assert gw.block_on is None
    assert gw.max_concurrent == 10
    assert gw.timeout == 300.0
    assert gw.vendor_override is None
    assert gw.backends == []
    assert gw.pipeline == ""


def test_gateway_sdk_middleware() -> None:
    settings = parse_settings_dict({"gateway": {"type": "sdk-middleware"}})
    assert settings.gateway.type == "sdk-middleware"


# ---------------------------------------------------------------------------
# Orchestrator settings defaults
# ---------------------------------------------------------------------------


def test_orchestrator_defaults() -> None:
    settings = parse_settings_dict({})
    orch = settings.orchestrator
    assert orch.type == "generic"
    assert orch.skill_detection is True
    assert orch.prompt_fingerprint is True
    assert orch.feedback.enabled is False
    assert orch.dataset.enabled is False


def test_orchestrator_full() -> None:
    settings = parse_settings_dict(
        {
            "backends": {"local": {"type": "jsonl", "path": "/tmp/out.jsonl"}},
            "orchestrator": {
                "type": "claude-code",
                "skill_detection": False,
                "prompt_fingerprint": False,
                "feedback": {"enabled": True, "backend": "local"},
                "dataset": {"enabled": True, "path": "/data/out.jsonl", "include_user_messages": True},
            },
        }
    )
    orch = settings.orchestrator
    assert orch.type == "claude-code"
    assert orch.skill_detection is False
    assert orch.feedback.enabled is True
    assert orch.feedback.backend == "local"
    assert orch.dataset.enabled is True
    assert orch.dataset.include_user_messages is True


# ---------------------------------------------------------------------------
# PromptLintSettings property accessors
# ---------------------------------------------------------------------------


def test_settings_property_accessors() -> None:
    settings = parse_settings_dict(
        {
            "pipelines": {"fast": {"metrics": ["scorer"]}},
        }
    )
    assert "fast" in settings.pipelines
    assert settings.stages == {}
    assert settings.benchmarks == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_gateway_with_no_backends_defined(tmp_path: Path) -> None:
    """Gateway references empty backends list — should pass."""
    cfg = tmp_path / "promptlint.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        version: 1
        gateway:
          type: builtin-proxy
          backends: []
    """)
    )
    settings = load_settings(cfg)
    assert settings.gateway.backends == []


def test_feedback_disabled_with_unknown_backend() -> None:
    """Feedback disabled does not validate backend reference."""
    settings = parse_settings_dict(
        {
            "orchestrator": {
                "type": "generic",
                "feedback": {"enabled": False, "backend": "nonexistent"},
            },
        }
    )
    # Should not raise since feedback is disabled
    assert settings.orchestrator.feedback.backend == "nonexistent"


def test_env_var_in_nested_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_LABEL", "production")
    settings = parse_settings_dict(
        {
            "backends": {
                "metrics": {
                    "type": "prometheus",
                    "labels": {"env": "${MY_LABEL}"},
                },
            },
        }
    )
    assert settings.backends["metrics"]["labels"]["env"] == "production"


def test_version_default_when_omitted() -> None:
    settings = parse_settings_dict({})
    assert settings.version == 1
