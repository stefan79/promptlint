"""Prometheus pushgateway emitter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult, Feedback

_METRIC_HELP = {
    "promptlint_instruction_count": "Total number of instructions detected",
    "promptlint_density": "Instructions per 1K tokens",
    "promptlint_contradiction_count": "Number of contradiction pairs detected",
}


class PrometheusEmitter:
    """Pushes analysis metrics to a Prometheus pushgateway."""

    def __init__(self, config: dict) -> None:
        self._pushgateway = config["pushgateway"].rstrip("/")
        self._job = config.get("job", "promptlint")
        self._timeout = config.get("timeout", 10)

    def write_analysis(self, result: AnalysisResult) -> None:
        lines = self._format_metrics(result)
        body = "\n".join(lines) + "\n"
        url = f"{self._pushgateway}/metrics/job/{self._job}"
        req = Request(url, data=body.encode("utf-8"), method="POST")
        req.add_header("Content-Type", "text/plain; version=0.0.4")
        with urlopen(req, timeout=self._timeout) as resp:
            resp.read()

    def write_feedback(self, feedback: Feedback) -> None:
        pass

    def _format_metrics(self, result: AnalysisResult) -> list[str]:
        labels = f'severity="{result.severity}"'
        lines: list[str] = []
        metrics = {
            "promptlint_instruction_count": float(result.instruction_count),
            "promptlint_density": result.density,
            "promptlint_contradiction_count": float(len(result.contradictions)),
        }
        for name, value in metrics.items():
            help_text = _METRIC_HELP.get(name, "")
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{{{labels}}} {value}")
        return lines
