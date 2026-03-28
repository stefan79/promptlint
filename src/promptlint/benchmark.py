"""Benchmark runner for pipeline comparison (spec 02)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from promptlint.pipeline import PipelineRunner
from promptlint.pipeline_config import BenchmarkDefinition, PipelineConfig  # noqa: TC001

if TYPE_CHECKING:
    from promptlint.models import AnalysisResult


@dataclass
class StageTimings:
    """Per-stage latency across iterations."""

    preprocessing_ms: list[float] = field(default_factory=list)
    metrics_ms: list[float] = field(default_factory=list)
    total_ms: list[float] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Benchmark results for a single pipeline."""

    pipeline: str
    iterations: int = 0
    timings: StageTimings = field(default_factory=StageTimings)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Full benchmark run output."""

    name: str
    corpus: str
    repeat: int
    corpus_files: list[str] = field(default_factory=list)
    results: list[PipelineResult] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())


def run_benchmark(
    benchmark_def: BenchmarkDefinition,
    pipeline_config: PipelineConfig,
    runner: PipelineRunner | None = None,
) -> BenchmarkResult:
    """Execute a benchmark: warm-up, then timed iterations."""
    if runner is None:
        runner = PipelineRunner(pipeline_config)

    # Load corpus
    corpus_path = Path(benchmark_def.corpus)
    if corpus_path.is_file():
        corpus_files = [corpus_path]
    elif corpus_path.is_dir():
        corpus_files = sorted(corpus_path.glob("*.md")) + sorted(corpus_path.glob("*.txt"))
    else:
        msg = f"Corpus path '{benchmark_def.corpus}' does not exist"
        raise FileNotFoundError(msg)

    corpus_texts = [(f.name, f.read_text()) for f in corpus_files]

    if not corpus_texts:
        msg = f"No .md or .txt files found in corpus '{benchmark_def.corpus}'"
        raise FileNotFoundError(msg)

    result = BenchmarkResult(
        name=benchmark_def.name,
        corpus=benchmark_def.corpus,
        repeat=benchmark_def.repeat,
        corpus_files=[name for name, _ in corpus_texts],
    )

    for pipeline_name in benchmark_def.pipelines:
        # Warm-up pass: run each pipeline once (excluded from timing)
        for _, text in corpus_texts:
            runner.run(pipeline_name, text)

        # Timed iterations
        pipeline_result = PipelineResult(pipeline=pipeline_name, iterations=benchmark_def.repeat)
        all_analysis_results: list[AnalysisResult] = []

        for _ in range(benchmark_def.repeat):
            iteration_start = time.perf_counter()

            for _, text in corpus_texts:
                analysis = runner.run(pipeline_name, text)
                all_analysis_results.append(analysis)

            iteration_ms = (time.perf_counter() - iteration_start) * 1000
            pipeline_result.timings.total_ms.append(iteration_ms)

        # Aggregate metrics from last iteration
        if all_analysis_results:
            last_results = all_analysis_results[-len(corpus_texts) :]
            pipeline_result.metrics = _aggregate_metrics(last_results, benchmark_def.metrics)

        # Compute latency percentiles
        totals = sorted(pipeline_result.timings.total_ms)
        if totals:
            pipeline_result.metrics["latency_p50"] = _percentile(totals, 50)
            pipeline_result.metrics["latency_p99"] = _percentile(totals, 99)

        result.results.append(pipeline_result)

    return result


def _aggregate_metrics(results: list[AnalysisResult], requested: list[str]) -> dict[str, float]:
    """Aggregate analysis metrics across corpus files."""
    aggregated: dict[str, float] = {}

    # Sum across all corpus files
    total_instructions = sum(r.instruction_count for r in results)
    total_contradictions = sum(len(r.contradictions) for r in results)
    total_redundancy = sum(r.redundancy_ratio for r in results) / max(len(results), 1)

    metric_map: dict[str, float] = {
        "instruction_count": total_instructions,
        "contradiction_count": total_contradictions,
        "redundancy_ratio": total_redundancy,
    }

    for key in requested:
        if key in metric_map:
            aggregated[key] = metric_map[key]

    return aggregated


def _percentile(sorted_values: list[float], pct: int) -> float:
    """Simple percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    idx = int(len(sorted_values) * pct / 100)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]
