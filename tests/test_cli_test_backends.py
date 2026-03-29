"""Tests for the test-backends CLI command."""

from __future__ import annotations

import sys
import textwrap

from promptlint.cli import main


def _run_test_backends(config_path: str) -> int:
    sys.argv = ["promptlint", "test-backends", "--config", config_path]
    try:
        main()
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    return 0


def test_test_backends_pass(tmp_path) -> None:
    jsonl_path = tmp_path / "out.jsonl"
    config = tmp_path / "config.yaml"
    config.write_text(
        textwrap.dedent(f"""\
            backends:
              local:
                type: jsonl
                path: {jsonl_path}
        """),
        encoding="utf-8",
    )

    exit_code = _run_test_backends(str(config))

    assert exit_code == 0
    assert jsonl_path.exists()


def test_test_backends_no_backends(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("other_key: true\n", encoding="utf-8")

    exit_code = _run_test_backends(str(config))

    assert exit_code == 1


def test_test_backends_invalid_type(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        textwrap.dedent("""\
            backends:
              bad:
                type: nonexistent
        """),
        encoding="utf-8",
    )

    exit_code = _run_test_backends(str(config))

    assert exit_code == 1


def test_test_backends_non_mapping_config(tmp_path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        textwrap.dedent("""\
            backends:
              bad: just-a-string
        """),
        encoding="utf-8",
    )

    exit_code = _run_test_backends(str(config))

    assert exit_code == 1
