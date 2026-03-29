"""Tests for gateway abstractions — capabilities, GatewayInfo, concurrency, AnalysisResult integration."""

from __future__ import annotations

from promptlint.gateways import (
    ConcurrencyConfig,
    GatewayCapability,
    GatewayInfo,
    PromptLintBlockedError,
    PromptLintOverloadError,
    VendorDetectionError,
)
from promptlint.models import AnalysisResult

# --- GatewayCapability ---


def test_capability_flag_combination() -> None:
    combined = GatewayCapability.LOG_ONLY | GatewayCapability.ANNOTATE | GatewayCapability.BLOCK
    assert GatewayCapability.LOG_ONLY in combined
    assert GatewayCapability.ANNOTATE in combined
    assert GatewayCapability.BLOCK in combined


def test_capability_log_only() -> None:
    cap = GatewayCapability.LOG_ONLY
    assert GatewayCapability.BLOCK not in cap
    assert GatewayCapability.ANNOTATE not in cap


# --- GatewayInfo ---


def test_gateway_info_defaults() -> None:
    info = GatewayInfo(type="builtin-proxy")
    assert info.type == "builtin-proxy"
    assert len(info.id) == 12  # uuid4 hex[:12]


def test_gateway_info_custom_id() -> None:
    info = GatewayInfo(type="sdk-middleware", id="my-custom-id")
    assert info.id == "my-custom-id"


# --- ConcurrencyConfig ---


def test_concurrency_config_default() -> None:
    config = ConcurrencyConfig()
    assert config.max_concurrent == 10


def test_concurrency_config_custom() -> None:
    config = ConcurrencyConfig(max_concurrent=5)
    assert config.max_concurrent == 5


# --- AnalysisResult with gateway field ---


def test_analysis_result_gateway_none_by_default() -> None:
    result = AnalysisResult()
    assert result.gateway is None


def test_analysis_result_with_gateway_info() -> None:
    info = GatewayInfo(type="builtin-proxy", id="test-123")
    result = AnalysisResult(gateway=info)
    assert result.gateway is not None
    assert result.gateway.type == "builtin-proxy"
    assert result.gateway.id == "test-123"


def test_analysis_result_to_json_includes_gateway() -> None:
    info = GatewayInfo(type="sdk-middleware", id="mid-1")
    result = AnalysisResult(gateway=info, severity="ok")
    json_str = result.to_json()
    assert "sdk-middleware" in json_str
    assert "mid-1" in json_str


def test_analysis_result_to_json_gateway_null() -> None:
    result = AnalysisResult(severity="ok")
    json_str = result.to_json()
    assert '"gateway": null' in json_str


# --- Exception classes ---


def test_blocked_error_has_result() -> None:
    result = AnalysisResult(severity="critical")
    err = PromptLintBlockedError(severity="critical", result=result)
    assert err.severity == "critical"
    assert err.result is result
    assert "critical" in str(err)


def test_overload_error() -> None:
    err = PromptLintOverloadError()
    assert isinstance(err, Exception)


def test_vendor_detection_error() -> None:
    err = VendorDetectionError("bad body")
    assert "bad body" in str(err)
