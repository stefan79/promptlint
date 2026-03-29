"""Integration tests for Prometheus pushgateway emitter (requires Docker)."""

from __future__ import annotations

from urllib.request import urlopen

import pytest

from promptlint.emitters.prometheus import PrometheusEmitter
from promptlint.models import AnalysisResult

PUSHGATEWAY_URL = "http://localhost:9091"


def _pushgateway_available() -> bool:
    try:
        with urlopen(f"{PUSHGATEWAY_URL}/-/healthy", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _get_metrics() -> str:
    with urlopen(f"{PUSHGATEWAY_URL}/metrics", timeout=5) as resp:
        return resp.read().decode("utf-8")


@pytest.mark.integration
def test_push_and_verify_metrics() -> None:
    if not _pushgateway_available():
        pytest.skip("Prometheus pushgateway not available")

    emitter = PrometheusEmitter({"pushgateway": PUSHGATEWAY_URL, "job": "integration-test"})
    result = AnalysisResult(instruction_count=10, density=25.0, severity="warning")

    emitter.write_analysis(result)

    metrics = _get_metrics()
    assert "promptlint_instruction_count" in metrics
    assert "promptlint_density" in metrics
