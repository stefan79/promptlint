"""CLI entry point for promptlint."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptlint import PromptAnalyzer
    from promptlint.models import AnalysisResult


def main() -> None:
    parser = argparse.ArgumentParser(prog="promptlint", description="Analyze LLM prompts for instruction hygiene.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a prompt file or stdin.")
    _add_common_args(analyze_parser)
    analyze_parser.add_argument("file", nargs="?", help="Prompt file to analyze (reads stdin if omitted).")
    analyze_parser.add_argument("--format", choices=["terminal", "json", "markdown"], default="terminal")

    # check command
    check_parser = subparsers.add_parser("check", help="Check prompt and exit with code 1 if threshold exceeded.")
    _add_common_args(check_parser)
    check_parser.add_argument("file", nargs="?", help="Prompt file to check.")
    check_parser.add_argument("--fail-on", choices=["warning", "critical"], default="critical")
    check_parser.add_argument("--format", choices=["terminal", "json", "markdown"], default="terminal")

    # diff command
    diff_parser = subparsers.add_parser("diff", help="Compare two prompt versions.")
    diff_parser.add_argument("old", help="Old prompt file.")
    diff_parser.add_argument("new", help="New prompt file.")
    diff_parser.add_argument("--format", choices=["terminal", "json"], default="terminal")

    # pipeline command
    pipeline_parser = subparsers.add_parser("pipeline", help="Run a named pipeline from a YAML config.")
    pipeline_parser.add_argument("file", help="Prompt file to analyze.")
    pipeline_parser.add_argument("--config", required=True, help="Path to pipeline YAML config.")
    pipeline_parser.add_argument("--pipeline", required=True, help="Name of the pipeline to run.")
    pipeline_parser.add_argument("--format", choices=["terminal", "json", "markdown"], default="terminal")

    # benchmark command
    benchmark_parser = subparsers.add_parser("benchmark", help="Run a benchmark comparing pipelines.")
    benchmark_parser.add_argument("--config", required=True, help="Path to pipeline YAML config.")
    benchmark_parser.add_argument("--benchmark", required=True, help="Name of the benchmark to run.")
    benchmark_parser.add_argument("--output", help="Path to write JSON results (default: stdout).")

    # proxy command
    proxy_parser = subparsers.add_parser("proxy", help="Start reverse proxy for live analysis.")
    proxy_parser.add_argument("--port", type=int, default=8100)
    proxy_parser.add_argument("--target", default="https://api.anthropic.com")
    proxy_parser.add_argument("--fail-on", choices=["warning", "critical"], default=None)
    _add_common_args(proxy_parser)

    args = parser.parse_args()

    if args.command == "analyze":
        _cmd_analyze(args)
    elif args.command == "check":
        _cmd_check(args)
    elif args.command == "diff":
        _cmd_diff(args)
    elif args.command == "pipeline":
        _cmd_pipeline(args)
    elif args.command == "benchmark":
        _cmd_benchmark(args)
    elif args.command == "proxy":
        _cmd_proxy(args)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--claude-md", help="Path to CLAUDE.md file.")
    parser.add_argument("--skills", help="Path to skills directory.")
    parser.add_argument("--warn-instructions", type=int, default=80)
    parser.add_argument("--critical-instructions", type=int, default=150)
    parser.add_argument("--warn-density", type=float, default=60.0)
    parser.add_argument("--critical-density", type=float, default=90.0)
    parser.add_argument("--classification-threshold", type=float, default=0.65)
    parser.add_argument("--contradiction-threshold", type=float, default=0.7)


def _build_analyzer(args: argparse.Namespace) -> PromptAnalyzer:
    from promptlint import PromptAnalyzer

    return PromptAnalyzer(
        warn_instructions=args.warn_instructions,
        critical_instructions=args.critical_instructions,
        warn_density=args.warn_density,
        critical_density=args.critical_density,
        classification_threshold=args.classification_threshold,
        contradiction_threshold=args.contradiction_threshold,
    )


def _get_result(args: argparse.Namespace) -> AnalysisResult:
    analyzer = _build_analyzer(args)

    if getattr(args, "claude_md", None) or getattr(args, "skills", None):
        return analyzer.analyze_files(
            claude_md=args.claude_md,
            skill_dirs=[args.skills] if args.skills else None,
        )

    text = _read_input(args)
    return analyzer.analyze(text=text)


def _read_input(args: argparse.Namespace) -> str:
    if args.file:
        with open(args.file) as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("Error: no input file provided and stdin is a terminal.", file=sys.stderr)
    sys.exit(1)


def _cmd_analyze(args: argparse.Namespace) -> None:
    result = _get_result(args)
    _print_result(result, args.format)


def _cmd_check(args: argparse.Namespace) -> None:
    result = _get_result(args)
    _print_result(result, args.format)

    severity_order = {"ok": 0, "warning": 1, "critical": 2}
    if severity_order.get(result.severity, 0) >= severity_order.get(args.fail_on, 2):
        sys.exit(1)


def _cmd_diff(args: argparse.Namespace) -> None:
    from promptlint import PromptAnalyzer

    analyzer = PromptAnalyzer()

    with open(args.old) as f:
        old_text = f.read()
    with open(args.new) as f:
        new_text = f.read()

    old_result = analyzer.analyze(text=old_text)
    new_result = analyzer.analyze(text=new_text)

    if args.format == "json":
        import json

        diff = {
            "old": {
                "instruction_count": old_result.instruction_count,
                "unique": old_result.unique_instruction_count,
                "density": old_result.density,
                "contradictions": len(old_result.contradictions),
                "severity": old_result.severity,
            },
            "new": {
                "instruction_count": new_result.instruction_count,
                "unique": new_result.unique_instruction_count,
                "density": new_result.density,
                "contradictions": len(new_result.contradictions),
                "severity": new_result.severity,
            },
            "delta": {
                "instruction_count": new_result.instruction_count - old_result.instruction_count,
                "unique": new_result.unique_instruction_count - old_result.unique_instruction_count,
                "density": round(new_result.density - old_result.density, 1),
                "contradictions": len(new_result.contradictions) - len(old_result.contradictions),
            },
        }
        print(json.dumps(diff, indent=2))
    else:
        _print_diff_terminal(old_result, new_result)


def _cmd_pipeline(args: argparse.Namespace) -> None:
    from promptlint.pipeline import PipelineRunner
    from promptlint.pipeline_config import load_config

    config = load_config(args.config)
    runner = PipelineRunner(config)

    with open(args.file) as f:
        text = f.read()

    result = runner.run(args.pipeline, text)
    _print_result(result, args.format)


def _cmd_benchmark(args: argparse.Namespace) -> None:
    from promptlint.benchmark import run_benchmark
    from promptlint.pipeline import PipelineRunner
    from promptlint.pipeline_config import load_config

    config = load_config(args.config)
    runner = PipelineRunner(config)

    benchmark_name = args.benchmark
    if benchmark_name not in config.benchmarks:
        print(f"Error: unknown benchmark '{benchmark_name}'. Available: {list(config.benchmarks)}", file=sys.stderr)
        sys.exit(1)

    benchmark_def = config.benchmarks[benchmark_name]
    result = run_benchmark(benchmark_def, config, runner)

    if args.output:
        result.save(args.output)
        print(f"Benchmark results written to {args.output}")
    else:
        print(result.to_json())


def _cmd_proxy(args: argparse.Namespace) -> None:
    import uvicorn

    from promptlint.proxy import create_app

    app = create_app(
        target=args.target,
        fail_on=args.fail_on,
        warn_instructions=args.warn_instructions,
        critical_instructions=args.critical_instructions,
        warn_density=args.warn_density,
        critical_density=args.critical_density,
        classification_threshold=args.classification_threshold,
        contradiction_threshold=args.contradiction_threshold,
    )
    print(f"promptlint proxy listening on http://localhost:{args.port}")
    print(f"Forwarding to {args.target}")
    if args.fail_on:
        print(f"Blocking requests with severity >= {args.fail_on}")
    print()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


def _print_result(result: AnalysisResult, fmt: str) -> None:
    if fmt == "json":
        print(result.to_json())
    elif fmt == "markdown":
        print(result.to_markdown())
    else:
        _print_terminal(result)


def _print_terminal(result: AnalysisResult) -> None:
    severity_icon = {"ok": "✅", "warning": "⚠️ ", "critical": "🚨"}
    icon = severity_icon.get(result.severity, "")

    print("promptlint v1.0 — Analysis Report")
    print("=" * 38)
    print()
    print(f"Severity: {icon} {result.severity.upper()}")
    print()
    print(f"Instructions:     {result.instruction_count} total, {result.unique_instruction_count} unique")

    total_dups = result.instruction_count - result.unique_instruction_count
    if total_dups > 0:
        print(
            f"Redundancy:       {total_dups} redundant ({result.redundancy_ratio:.1%}) across {len(result.redundant_groups)} groups"
        )
    else:
        print("Redundancy:       none detected")

    print(f"Contradictions:   {len(result.contradictions)} pairs detected")
    print(f"Density:          {result.density:.1f} instructions / 1K tokens")

    if result.section_distribution:
        print()
        print("Section Breakdown:")
        for section, count in sorted(result.section_distribution.items(), key=lambda x: -x[1]):
            pct = (count / result.instruction_count * 100) if result.instruction_count else 0
            print(f"  {section:<20s} {count:>3d} instructions  ({pct:4.1f}%)")

    if result.redundant_groups:
        print()
        print("Top Redundancy Groups:")
        for i, group in enumerate(result.redundant_groups[:5], 1):
            texts = [f'"{group.canonical.text[:50]}"'] + [f'"{d.text[:50]}"' for d in group.duplicates]
            print(f"  {i}. {' ≈ '.join(texts)} ({len(group.duplicates) + 1} instances)")

    if result.contradictions:
        print()
        print("Contradictions:")
        for i, c in enumerate(result.contradictions, 1):
            print(f'  {i}. [{c.score:.2f}] "{c.instruction_a.text[:60]}" ↔ "{c.instruction_b.text[:60]}"')
            print(f"            {c.instruction_a.source_section} ↔ {c.instruction_b.source_section}")

    if result.warnings:
        print()
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    print()


def _print_diff_terminal(old: AnalysisResult, new: AnalysisResult) -> None:
    def _delta(a: int | float, b: int | float) -> str:
        d = b - a
        return f"+{d}" if d > 0 else str(d)

    print("promptlint v1.0 — Diff Report")
    print("=" * 38)
    print()
    print(f"{'Metric':<25s} {'Old':>8s} {'New':>8s} {'Delta':>8s}")
    print("-" * 52)
    print(
        f"{'Instructions':<25s} {old.instruction_count:>8d} {new.instruction_count:>8d} {_delta(old.instruction_count, new.instruction_count):>8s}"
    )
    print(
        f"{'Unique instructions':<25s} {old.unique_instruction_count:>8d} {new.unique_instruction_count:>8d} {_delta(old.unique_instruction_count, new.unique_instruction_count):>8s}"
    )
    print(
        f"{'Density':<25s} {old.density:>8.1f} {new.density:>8.1f} {_delta(round(old.density, 1), round(new.density, 1)):>8s}"
    )
    print(
        f"{'Contradictions':<25s} {len(old.contradictions):>8d} {len(new.contradictions):>8d} {_delta(len(old.contradictions), len(new.contradictions)):>8s}"
    )
    print(f"{'Severity':<25s} {old.severity:>8s} {new.severity:>8s}")
    print()


if __name__ == "__main__":
    main()
